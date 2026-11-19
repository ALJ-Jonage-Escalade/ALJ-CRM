import { fakeAuth, json, provided } from "../test/harness";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { type ApiFetch } from "../lib/api";
import type { Role } from "../lib/roles";
import { routes } from "../router";
import type { Slot } from "./planning/slots";
import { dialogs } from "../composables/dialogs";

const SLOT = (change: Partial<Slot>): Slot => ({
  id: 1,
  groupe: "Loisir",
  type: "cours",
  categorie_age: "",
  jour: "Lundi",
  horaires: "18:00 - 20:00",
  encadrants: [],
  helloasso_tarifs: [],
  whatsapp_link: "",
  naissance_min: "",
  naissance_max: "",
  ...change,
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

async function render(role: Role = "admin", answers: Record<string, Answer> = ANSWERS, path = "/bureau/planning") {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path: u.pathname + u.search, body });
    const answer = answers[`${method} ${u.pathname}`];
    return answer ? answer(body) : json({}, 404);
  });
  const auth = fakeAuth({ status: "signedIn", user: { uid: "u1", email: "u@alj.example" }, role });
  // The app's routes: the page renders its sub-pages (router.ts)
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push(path);
  const wrapper = mount(RouterView, {
    attachTo: document.body,
    global: {
      plugins: [router],
      provide: provided(auth, api),
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  // The dialog and the export menu are rendered at the end of <body>
  const byId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const all = (id: string) => [...document.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`)];
  const writes = () => calls.filter((c) => c.method !== "GET");
  // The sub-menu links are stubbed (PageLink): opened through the router, as PageLink does
  const open = async (sub: "semaine" | "tableau") => {
    await router.push(sub === "semaine" ? "/bureau/planning" : `/bureau/planning/${sub}`);
    await flushPromises();
  };
  return { wrapper, router, calls, writes, byId, all, open };
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("PlanningPage", () => {
  it("shows the week, then the table with its filters", async () => {
    const { byId, all, open } = await render();
    await flushPromises();
    expect(byId("slot-count")!.textContent).toBe("3 créneaux configurés");
    // The two-day slot has no column
    expect(all("slot-card").map((c) => c.querySelector("b")!.textContent)).toEqual(["Loisir collège", "Compétition U13"]);
    expect(byId("day-Mercredi")!.textContent).toContain("Compétition U13");

    await open("tableau");
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

    // The table keeps its filters while the week is shown (sub-pages kept mounted)
    await open("semaine");
    await open("tableau");
    expect(all("slot-row")).toHaveLength(1);
  });

  it("prints the week grid, opened first from the table", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    const { byId, router } = await render("admin", ANSWERS, "/bureau/planning/tableau");
    byId("planning-print")!.click();
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/bureau/planning");
    expect(byId("day-Lundi")).not.toBeNull();
    expect(print).toHaveBeenCalledOnce();
  });

  it("creates a slot from the dialog", async () => {
    const { byId, writes, calls } = await render();
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
    expect(writes()).toEqual([
      {
        method: "POST",
        path: "/api/planning/item",
        body: {
          id: 0,
          groupe: "Stage d'été",
          jour: "Lundi",
          horaires: "18:00 - 20:00",
          type: "cours",
          categorie_age: "",
          encadrants: ["Remus Lupin", "Rubeus Hagrid"],
          helloasso_tarifs: [],
          whatsapp_link: "",
          naissance_min: "",
          naissance_max: "",
        },
      },
    ]);
    expect(byId("toast")!.textContent).toBe("✅ Créneau « Stage d'été » enregistré !");
    expect(byId("slot-dialog")).toBeNull();
    expect(calls.filter((c) => c.path === "/api/planning")).toHaveLength(2); // reloaded
  });

  it("edits a slot from its card, and shows a refusal", async () => {
    const { byId, all, writes } = await render("admin", {
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
    const { byId, writes } = await render();
    await flushPromises();
    byId("slot-new")!.click();
    await flushPromises();
    byId("slot-save")!.click();
    await flushPromises();
    expect(writes()).toEqual([]);
    expect(byId("toast")!.textContent).toBe("⚠️ Le nom du groupe est obligatoire.");
  });

  it("deletes a slot once confirmed", async () => {
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const { byId, all, writes } = await render("admin", ANSWERS, "/bureau/planning/tableau");
    await flushPromises();
    all("slot-delete")[1]!.click();
    expect(writes()).toEqual([]);
    all("slot-delete")[1]!.click();
    await flushPromises();
    expect(confirm).toHaveBeenLastCalledWith(
      expect.objectContaining({ message: "Voulez-vous vraiment supprimer le créneau « Compétition U13 » (Mercredi 18:00 - 20:00) ?" }),
    );
    expect(writes()).toEqual([{ method: "DELETE", path: "/api/planning/item/2", body: undefined }]);
    expect(byId("toast")!.textContent).toBe("🗑️ Créneau supprimé.");
  });

  it("lets a coach change the slots too", async () => {
    const { byId, all, writes } = await render("coach");
    await flushPromises();
    expect(byId("slot-new")).not.toBeNull();
    all("slot-card")[0]!.click();
    await flushPromises();
    byId("slot-save")!.click();
    await flushPromises();
    expect(writes()[0]).toMatchObject({ method: "POST", path: "/api/planning/item", body: { id: 1 } });
  });

  it("says when the planning cannot be loaded", async () => {
    const { byId } = await render("admin", {
      ...ANSWERS,
      "GET /api/planning": () => json({ status: "error", message: "Erreur interne." }, 500),
    });
    await flushPromises();
    expect(byId("slot-count")!.textContent).toBe("Erreur chargement");
    expect(byId("toast")!.textContent).toBe("❌ Impossible de charger le planning : Erreur interne.");
  });
});
