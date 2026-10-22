import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { AUTH_KEY, type Auth } from "../composables/auth";
import { API_KEY, type ApiFetch } from "../lib/api";
import { CLIENT_KEY, createApiClient } from "../lib/client";
import type { Role } from "../lib/roles";
import PlanningPage from "./PlanningPage.vue";
import type { Slot } from "./planning/slots";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const SLOT = (change: Partial<Slot>): Slot => ({
  id: 1, groupe: "Loisir", type: "cours", categorie_age: "", jour: "Lundi", horaires: "18:00 - 20:00",
  encadrants: [], helloasso_tarifs: [], whatsapp_link: "", naissance_min: "", naissance_max: "", ...change,
});
const SLOTS = [
  SLOT({ id: 1, groupe: "Loisir collège", encadrants: ["Remus Lupin"] }),
  SLOT({ id: 2, groupe: "Compétition U13", type: "compétition", jour: "Mercredi" }),
  SLOT({ id: 3, groupe: "Autonome", type: "autonome", jour: "Lundi / Jeudi" }),
];

type Answer = (body: unknown) => Response;
const ANSWERS: Record<string, Answer> = {
  "GET /api/planning": () => json(SLOTS),
  "GET /api/season-tarifs": () => json({ status: "success", season: "2026-2027", tarifs: ["Licence sèche"] }),
  "POST /api/planning/item": (body) => json({ status: "success", message: "ok", item: { ...SLOT({}), ...(body as object), id: 9 } }),
  "DELETE /api/planning/item/2": () => json({ status: "success", message: "ok" }),
};

function render(role: Role = "admin", answers: Record<string, Answer> = ANSWERS) {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path: u.pathname + u.search, body });
    const answer = answers[`${method} ${u.pathname}`];
    return answer ? answer(body) : json({}, 404);
  });
  const auth: Auth = {
    state: ref({ status: "signedIn", user: { uid: "u1", email: "u@alj.example" }, role }),
    login: vi.fn(), logout: vi.fn(async () => {}), retry: vi.fn(async () => {}), stop: vi.fn(),
  };
  const wrapper = mount(PlanningPage, {
    attachTo: document.body,
    global: {
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") },
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  // The dialog and the export menu are rendered at the end of <body>
  const byId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const all = (id: string) => [...document.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`)];
  const writes = () => calls.filter((c) => c.method !== "GET");
  return { wrapper, calls, writes, byId, all };
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("PlanningPage", () => {
  it("shows the week, then the table with its filters", async () => {
    const { byId, all } = render();
    await flushPromises();
    expect(byId("slot-count")!.textContent).toBe("3 créneau(x) configuré(s)");
    // The two-day slot has no column
    expect(all("slot-card").map((c) => c.querySelector("b")!.textContent)).toEqual(["Loisir collège", "Compétition U13"]);
    expect(byId("day-Mercredi")!.textContent).toContain("Compétition U13");

    byId("view-table")!.click();
    await flushPromises();
    expect(all("slot-row")).toHaveLength(3);
    const search = byId("slot-search") as HTMLInputElement;
    search.value = "lupin";
    search.dispatchEvent(new Event("input"));
    await flushPromises();
    expect(all("slot-row").map((r) => r.querySelector("b")!.textContent)).toEqual(["Loisir collège"]);
    search.value = "";
    search.dispatchEvent(new Event("input"));
    byId("kind-compétition")!.click();
    await flushPromises();
    expect(all("slot-row")).toHaveLength(1);
  });

  it("creates a slot from the dialog", async () => {
    const { byId, writes, calls } = render();
    await flushPromises();
    byId("slot-new")!.click();
    await flushPromises();
    expect(document.body.textContent).toContain("➕ Nouveau créneau");
    const name = byId("slot-groupe") as HTMLInputElement;
    name.value = "Stage d'été";
    name.dispatchEvent(new Event("input"));
    const coaches = byId("slot-encadrants") as HTMLInputElement;
    coaches.value = "Remus Lupin, Rubeus Hagrid";
    coaches.dispatchEvent(new Event("input"));
    byId("slot-save")!.click();
    await flushPromises();
    expect(writes()).toEqual([{
      method: "POST",
      path: "/api/planning/item",
      body: {
        id: 0, groupe: "Stage d'été", jour: "Lundi", horaires: "18:00 - 20:00", type: "cours", categorie_age: "",
        encadrants: ["Remus Lupin", "Rubeus Hagrid"], helloasso_tarifs: [], whatsapp_link: "", naissance_min: "", naissance_max: "",
      },
    }]);
    expect(byId("toast")!.textContent).toBe("✅ Créneau « Stage d'été » enregistré !");
    expect(byId("slot-dialog")).toBeNull();
    expect(calls.filter((c) => c.path === "/api/planning")).toHaveLength(2);  // reloaded
  });

  it("edits a slot from its card, and shows a refusal", async () => {
    const { byId, all, writes } = render("admin", {
      ...ANSWERS,
      "POST /api/planning/item": () => json({ status: "error", message: "Les horaires sont obligatoires." }, 400),
    });
    await flushPromises();
    all("slot-card")[1]!.click();
    await flushPromises();
    expect(document.body.textContent).toContain("✏️ Modifier le créneau #2");
    expect((byId("slot-groupe") as HTMLInputElement).value).toBe("Compétition U13");
    byId("slot-save")!.click();
    await flushPromises();
    expect(writes()[0]!.body).toMatchObject({ id: 2, groupe: "Compétition U13", jour: "Mercredi" });
    expect(byId("toast")!.textContent).toBe("❌ Échec : Les horaires sont obligatoires.");
    expect(byId("slot-dialog")).not.toBeNull();
  });

  it("does not send a slot without a name", async () => {
    const { byId, writes } = render();
    await flushPromises();
    byId("slot-new")!.click();
    await flushPromises();
    byId("slot-save")!.click();
    await flushPromises();
    expect(writes()).toEqual([]);
    expect(byId("toast")!.textContent).toBe("⚠️ Le nom du groupe est obligatoire.");
  });

  it("deletes a slot once confirmed", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const { byId, all, writes } = render();
    await flushPromises();
    byId("view-table")!.click();
    await flushPromises();
    all("slot-delete")[1]!.click();
    expect(writes()).toEqual([]);
    all("slot-delete")[1]!.click();
    await flushPromises();
    expect(confirm).toHaveBeenLastCalledWith("Voulez-vous vraiment supprimer le créneau « Compétition U13 » (Mercredi 18:00 - 20:00) ?");
    expect(writes()).toEqual([{ method: "DELETE", path: "/api/planning/item/2", body: undefined }]);
    expect(byId("toast")!.textContent).toBe("🗑️ Créneau supprimé.");
  });

  it("lets a coach change the slots too", async () => {
    const { byId, all, writes } = render("coach");
    await flushPromises();
    expect(byId("slot-new")).not.toBeNull();
    all("slot-card")[0]!.click();
    await flushPromises();
    byId("slot-save")!.click();
    await flushPromises();
    expect(writes()[0]).toMatchObject({ method: "POST", path: "/api/planning/item", body: { id: 1 } });
  });

  it("says when the planning cannot be loaded", async () => {
    const { byId } = render("admin", { ...ANSWERS, "GET /api/planning": () => json({ status: "error", message: "Erreur interne." }, 500) });
    await flushPromises();
    expect(byId("slot-count")!.textContent).toBe("Erreur chargement");
    expect(byId("toast")!.textContent).toBe("❌ Impossible de charger le planning : Erreur interne.");
  });
});
