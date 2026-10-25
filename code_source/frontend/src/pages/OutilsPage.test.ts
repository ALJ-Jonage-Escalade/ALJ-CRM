import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { AUTH_KEY, type Auth } from "../composables/auth";
import { API_KEY, type ApiFetch } from "../lib/api";
import { CLIENT_KEY, createApiClient } from "../lib/client";
import type { Role } from "../lib/roles";
import OutilsPage from "./OutilsPage.vue";
import { dialogs } from "../composables/dialogs";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function file(name: string): Response {
  return new Response(new Blob(["x"]), { headers: { "Content-Disposition": `attachment; filename="${name}"` } });
}

const CONFIG = {
  status: "success",
  season: "2026-2027",
  default_dates: { start: "07/09/2026", end: "27/06/2027" },
  autonome: { adultes: 12, mineurs: 3, mineurs_autorises: 2, total: 17, groups: ["Autonome"] },
  cours: [
    { groupe: "Loisir collège", slots: "Lundi 18:00 - 20:00", tarifs: ["Loisir"], count: 8 },
    { groupe: "Compétition U13", slots: "", tarifs: ["Compet"], count: 5 },
  ],
};
const STATS = {
  status: "success",
  season: "2026-2027",
  produced_count: 20,
  termine_count: 10,
  ignored_count: 2,
  estimated_total: 30,
  renewals_count: 18,
  new_licences_count: 12,
  ignored_details: ["PETIT Max (date de naissance manquante/invalide)"],
};
const PREVIEW = {
  status: "success",
  filename: "ffme.xlsx",
  matched_count: 3,
  unmatched_count: 1,
  stats: { total_processed: 4, matched_by_licence: 2, matched_by_name: 1, matched_manually: 0, errors: [] },
  unmatched: [
    {
      nom: "DUPONT",
      prenom: "Tom",
      licence: "998877",
      birth_date: "22/07/2009",
      passeports: "",
      diplomes: "",
      document_sante: "Certificat",
    },
  ],
  users: [
    { id: 7, last_name: "PETIT", first_name: "Max", birth_date: "2009-07-22" },
    { id: 4, last_name: "DURAND", first_name: "Léa", birth_date: "" },
  ],
};

type Answer = (body: unknown, url: URL) => Response;
const ANSWERS: Record<string, Answer> = {
  "GET /api/seasons": () => json({ seasons: ["2026-2027", "2025-2026"], active: "2026-2027" }),
  "GET /map": () => new Response("<p>carte</p>"),
  "GET /pivot": (_, url) => new Response(`<p>tcd ${url.searchParams.get("season")}</p>`),
  "GET /api/presence/config": () => json(CONFIG),
  "POST /api/presence/export": () => file("Feuilles.xlsx"),
  "GET /api/ffme/stats": () => json(STATS),
  "GET /api/ffme/export": () => file("import_ffme_20261022.csv"),
  "POST /api/ffme/preview": () => json(PREVIEW),
  "POST /api/ffme/import": () =>
    json({
      status: "success",
      message: "Importation FFME validée : 4 adhérents mis à jour.",
      updated_count: 4,
      matched_manually: 1,
      season: "2026-2027",
      stats: PREVIEW.stats,
    }),
};

async function render(role: Role = "admin", path = "/bureau/outils") {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url, "http://alj.test");
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path: u.pathname + u.search, body });
    const answer = ANSWERS[`${method} ${u.pathname}`];
    return answer ? answer(body, u) : json({}, 404);
  });
  const auth: Auth = {
    state: ref({ status: "signedIn", user: { uid: "u1", email: "u@alj.example" }, role }),
    login: vi.fn(),
    logout: vi.fn(async () => {}),
    retry: vi.fn(async () => {}),
    stop: vi.fn(),
  };
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/bureau/outils", component: OutilsPage }] });
  await router.push(path);
  const wrapper = mount(OutilsPage, {
    attachTo: document.body,
    global: {
      plugins: [router],
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") },
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  await flushPromises();
  const byId = <T extends HTMLElement = HTMLElement>(id: string) => document.querySelector<T>(`[data-testid="${id}"]`);
  const all = (id: string) => [...document.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`)];
  const open = async (tab: string) => {
    byId(`tab-${tab}`)!.click();
    await flushPromises();
  };
  const sent = (method: string, path: string) => calls.filter((c) => c.method === method && c.path.startsWith(path));
  return { wrapper, router, calls, sent, byId, all, open };
}

function stubDownloads() {
  const created = vi.fn(() => "blob:x");
  Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  return created;
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("OutilsPage", () => {
  it("shows the map in a frame without same-origin, then the pivot table of the active season", async () => {
    const { byId, open, router, sent } = await render();
    const map = byId<HTMLIFrameElement>("map-frame")!;
    expect(map.getAttribute("srcdoc")).toBe("<p>carte</p>");
    expect(map.getAttribute("sandbox")).toBe("allow-scripts allow-popups");

    await open("pivot");
    expect(router.currentRoute.value.fullPath).toBe("/bureau/outils?tab=pivot");
    const pivot = byId<HTMLIFrameElement>("pivot-frame")!;
    expect(pivot.getAttribute("sandbox")).toBe("allow-scripts allow-popups allow-modals");
    expect(pivot.getAttribute("srcdoc")).toBe("<p>tcd 2026-2027</p>");
    expect([...byId<HTMLSelectElement>("pivot-season")!.options].map((o) => o.value)).toEqual([
      "2026-2027",
      "2025-2026",
      "Toutes les saisons",
    ]);

    const select = byId<HTMLSelectElement>("pivot-season")!;
    select.value = "Toutes les saisons";
    select.dispatchEvent(new Event("change"));
    await flushPromises();
    expect(pivot.getAttribute("srcdoc")).toBe("<p>tcd Toutes les saisons</p>");

    // The map stays loaded: back to it, no new request
    await open("map");
    expect(router.currentRoute.value.fullPath).toBe("/bureau/outils");
    expect(sent("GET", "/map")).toHaveLength(1);
    byId("tools-refresh")!.click();
    await flushPromises();
    expect(sent("GET", "/map")).toHaveLength(2);
    expect(byId("toast")!.textContent).toBe("🔄 Carte réactualisée.");
  });

  it("says when a tool page fails", async () => {
    const original = ANSWERS["GET /map"]!;
    ANSWERS["GET /map"] = () => new Response("", { status: 500 });
    try {
      const { byId } = await render();
      expect(byId("map-frame-status")!.textContent).toBe("❌ Erreur lors du chargement (HTTP 500).");
    } finally {
      ANSWERS["GET /map"] = original;
    }
  });

  it("opens the tab named in the URL; the import is for admins only", async () => {
    const admin = await render("admin", "/bureau/outils?tab=ffme-import");
    expect(admin.byId("pane-ffme-import")).not.toBeNull();
    expect(admin.sent("GET", "/map")).toHaveLength(0);
    admin.wrapper.unmount();
    document.body.innerHTML = "";

    const coach = await render("coach", "/bureau/outils?tab=ffme-import");
    expect(coach.byId("tab-ffme-import")).toBeNull();
    expect(coach.byId("pane-ffme-import")).toBeNull();
    expect(coach.byId("tab-map")!.getAttribute("aria-pressed")).toBe("true");
  });

  it("generates the attendance sheets", async () => {
    stubDownloads();
    const { byId, all, open, sent } = await render("coach", "/bureau/outils?tab=presence");
    expect(byId("presence-autonomous-summary")!.textContent).toContain("Total adhérents : 17");
    expect(byId("course-count")!.textContent.trim()).toBe("2 créneau(x)");
    expect(all("course").map((c) => (c as HTMLInputElement).checked)).toEqual([true, true]);
    expect(byId<HTMLInputElement>("courses-start")!.value).toBe("07/09/2026");

    byId("download-autonomous")!.click();
    await flushPromises();
    expect(sent("POST", "/api/presence/export").at(-1)!.body).toEqual({
      variant: "autonome",
      start_date: "07/09/2026",
      end_date: "27/06/2027",
      show_health_col: false,
    });
    expect(byId("toast")!.textContent).toBe("✅ Fichier « Feuilles.xlsx » téléchargé !");

    byId("courses-none")!.click();
    await flushPromises();
    byId("download-courses")!.click();
    await flushPromises();
    expect(byId("toast")!.textContent).toBe("⚠️ Veuillez cocher au moins un groupe de cours.");
    expect(sent("POST", "/api/presence/export")).toHaveLength(1);

    all("course")[1]!.click();
    byId("courses-zip")!.click();
    byId("courses-health")!.click();
    await flushPromises();
    byId("download-courses")!.click();
    await flushPromises();
    expect(sent("POST", "/api/presence/export").at(-1)!.body).toEqual({
      variant: "cours",
      selected_groups: ["Compétition U13"],
      start_date: "07/09/2026",
      end_date: "27/06/2027",
      same_sheet: false,
      show_health_col: true,
    });
    await open("ffme");
    await open("presence");
    expect(sent("GET", "/api/presence/config")).toHaveLength(1);
  });

  it("shows the FFME counts and downloads the CSV", async () => {
    stubDownloads();
    const { byId, sent } = await render("coach", "/bureau/outils?tab=ffme");
    expect(["ffme-total", "ffme-renewals", "ffme-new", "ffme-ignored"].map((id) => byId(id)!.textContent)).toEqual(["30", "18", "12", "2"]);
    expect(byId("ffme-ignored-details")!.textContent).toContain("PETIT Max (date de naissance manquante/invalide)");

    byId("ffme-include-finished")!.click();
    byId("ffme-download")!.click();
    await flushPromises();
    expect(sent("GET", "/api/ffme/export").at(-1)!.path).toBe("/api/ffme/export?include_termine=false");
    expect(byId("toast")!.textContent).toBe("✅ Fichier FFME « import_ffme_20261022.csv » téléchargé !");
  });

  it("previews the FFME file, then applies it with a manual match", async () => {
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const { byId, all, sent } = await render("admin", "/bureau/outils?tab=ffme-import");
    expect((byId("ffme-analyze") as HTMLButtonElement).disabled).toBe(true);

    const input = byId<HTMLInputElement>("ffme-file")!;
    Object.defineProperty(input, "files", { value: [new File(["not xlsx"], "liste.csv")], configurable: true });
    input.dispatchEvent(new Event("change"));
    await flushPromises();
    expect(byId("toast")!.textContent).toBe("⚠️ Seuls les fichiers Excel .xlsx sont acceptés.");

    Object.defineProperty(input, "files", { value: [new File(["PK"], "ffme.xlsx")], configurable: true });
    input.dispatchEvent(new Event("change"));
    await flushPromises();
    expect(byId("ffme-file-name")!.textContent).toBe("📄 Fichier sélectionné : ffme.xlsx (0 Ko)");

    byId("ffme-analyze")!.click();
    await flushPromises();
    expect(sent("POST", "/api/ffme/preview")[0]!.body).toEqual({ filename: "ffme.xlsx", content_base64: btoa("PK") });
    expect(byId("ffme-unmatched-count")!.textContent).toBe("1");
    const select = byId<HTMLSelectElement>("ffme-match")!;
    // Members in alphabetical order, after "ignore"
    expect([...select.options].map((o) => o.text)).toEqual(["-- Ignorer cette ligne --", "DURAND Léa (—)", "PETIT Max (2009-07-22)"]);
    select.selectedIndex = 2;
    select.dispatchEvent(new Event("change"));

    byId("ffme-apply")!.click();
    await flushPromises();
    expect(confirm).toHaveBeenLastCalledWith(
      expect.objectContaining({
        message:
          "Confirmer l'enregistrement de 4 adhérents en base de données ?\n\n• 3 réconciliés automatiquement\n• 1 associés manuellement",
      }),
    );
    expect(sent("POST", "/api/ffme/import")[0]!.body).toEqual({
      filename: "ffme.xlsx",
      content_base64: btoa("PK"),
      manual_matches: [
        { user_id: 7, nom: "DUPONT", prenom: "Tom", licence: "998877", passeports: "", diplomes: "", document_sante: "Certificat" },
      ],
    });
    expect(byId("ffme-import-done")!.textContent).toContain("4 adhérents ont été mis à jour");
    expect(all("ffme-preview")).toHaveLength(0);
  });

  it("imports straight away once confirmed", async () => {
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const { byId, sent } = await render("admin", "/bureau/outils?tab=ffme-import");
    const input = byId<HTMLInputElement>("ffme-file")!;
    Object.defineProperty(input, "files", { value: [new File(["PK"], "ffme.xlsx")], configurable: true });
    input.dispatchEvent(new Event("change"));
    await flushPromises();

    byId("ffme-quick-import")!.click();
    await flushPromises();
    expect(sent("POST", "/api/ffme/import")).toHaveLength(0);
    byId("ffme-quick-import")!.click();
    await flushPromises();
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(sent("POST", "/api/ffme/import")[0]!.body).toEqual({ filename: "ffme.xlsx", content_base64: btoa("PK"), manual_matches: [] });
    expect(byId("toast")!.textContent).toBe("🎉 Importation FFME validée : 4 adhérents mis à jour.");
  });
});
