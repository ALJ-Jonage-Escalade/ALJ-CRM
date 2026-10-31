import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { AUTH_KEY, type Auth } from "../composables/auth";
import { API_KEY, type ApiFetch } from "../lib/api";
import { CLIENT_KEY, createApiClient } from "../lib/client";
import type { Role } from "../lib/roles";
import { routes } from "../router";
import { dialogs } from "../composables/dialogs";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function file(name: string): Response {
  return new Response(new Blob(["x"]), { headers: { "Content-Disposition": `attachment; filename="${name}"` } });
}

const POINTS = [
  {
    address: "1 rue des Lilas, 69330 JONAGE",
    lat: 45.795,
    lon: 5.045,
    members: [
      { name: "Ginny WEASLEY", group: "Compet" },
      { name: "Ron WEASLEY", group: "Loisir" },
    ],
  },
  { address: "MEYZIEU", lat: 45.77, lon: 5.0, members: [{ name: "Luna LOVEGOOD", group: "Loisir" }] },
];
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

const MEMBERSHIP_PREVIEW = {
  status: "success",
  season: "2026-2027",
  campaign: "adhesion-escalade-2026-2027-amicale-laique-escalade-2",
  blocked_reason: null,
  counts: { already_imported: 0, new: 1, renewal: 0, updated: 0, to_review: 0, blocked: 1 },
  rows: [
    {
      item_id: 1,
      bucket: "new",
      reason: "Personne inconnue du club : nouvel adhérent.",
      order_ref: "501",
      order_date: "2026-09-01T10:00:00+02:00",
      payment_date: "2026-09-01T10:05:00+02:00",
      refund_date: "",
      last_name: "WEASLEY",
      first_name: "Ginny",
      birth_date: "2013-08-11",
      licence: "",
      tarif_name: "Loisir collège",
      amount: 150,
      status: "Processed",
      candidates: [],
      can_create: true,
      changes: [],
    },
    {
      item_id: 2,
      bucket: "blocked",
      reason: "Date de naissance manquante ou illisible.",
      order_ref: "502",
      order_date: "2026-09-01T10:00:00+02:00",
      payment_date: "2026-09-01T10:05:00+02:00",
      refund_date: "",
      last_name: "LOVEGOOD",
      first_name: "Luna",
      birth_date: "",
      licence: "",
      tarif_name: "Adultes autonomes",
      amount: 120,
      status: "Processed",
      candidates: [],
      can_create: false,
      changes: [],
    },
  ],
};
const REVIEW_ROW = {
  ...MEMBERSHIP_PREVIEW.rows[0]!,
  item_id: 3,
  bucket: "to_review",
  reason: "Même nom et prénom qu'un adhérent, mais date de naissance différente.",
  last_name: "GRANGER",
  first_name: "Hermione",
  birth_date: "2013-09-19",
  candidates: [{ user_id: 4, last_name: "GRANGER", first_name: "Hermione", birth_date: "2012-09-19", licence: "123456" }],
  can_create: true,
};

function membershipForm(slug: string, title: string, state: string, active = false) {
  return {
    form_type: "Membership",
    slug,
    title,
    private_title: "",
    state,
    activity_type: "",
    url: "",
    start_date: null,
    end_date: null,
    created_at: null,
    active,
    warning: null,
  };
}
const MEMBERSHIP_CAMPAIGNS = {
  error: null,
  warning: null,
  others: [],
  competitions: { active: null, configured: false, campaigns: [] },
  membership: {
    active: { form_type: "Membership", slug: "adhesion-escalade-2026-2027-amicale-laique-escalade-2" },
    configured: true,
    campaigns: [
      membershipForm("adhesion-escalade-2026-2027-amicale-laique-escalade-2", "Adhésions 2026-2027", "Public", true),
      membershipForm("adhesions-bis-2026-2027", "Adhésions de janvier", "Draft"),
    ],
  },
};

type Answer = (body: unknown, url: URL) => Response;
const ANSWERS: Record<string, Answer> = {
  "GET /api/seasons": () => json({ seasons: ["2026-2027", "2025-2026"], active: "2026-2027" }),
  "GET /api/reports/map-points": (_, url) => json({ season: url.searchParams.get("season"), points: POINTS }),
  "GET /api/reports/pivot-records": (_, url) => json({ season: url.searchParams.get("season"), records: [] }),
  "GET /api/presence/config": () => json(CONFIG),
  "POST /api/presence/export": () => file("Feuilles.xlsx"),
  "GET /api/ffme/stats": () => json(STATS),
  "POST /api/helloasso/memberships/preview": () => json(MEMBERSHIP_PREVIEW),
  "GET /api/helloasso/memberships/last-sync": () => json({ last_sync: null }),
  "GET /api/helloasso/campaigns": () => json(MEMBERSHIP_CAMPAIGNS),
  "POST /api/helloasso/memberships/import": () =>
    json({
      status: "success",
      season: "2026-2027",
      history_id: "2026-10-31T09:15:00+00:00-abcd1234",
      counts: { created: 1, renewed: 1, updated: 0, skipped: 1 },
      created: [{ item_id: 1, user_id: 7, purchase_id: 12, last_name: "WEASLEY", first_name: "Ginny", tarif_name: "Loisir collège" }],
      renewed: [{ item_id: 3, user_id: 4, purchase_id: 13, last_name: "GRANGER", first_name: "Hermione", tarif_name: "Compétition" }],
      updated: [],
    }),
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
  // The app's routes: the page renders its sub-pages (router.ts)
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push(path);
  const wrapper = mount(RouterView, {
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
  // The sub-menu links are stubbed (PageLink): opened through the router, as PageLink does
  const open = async (sub: string) => {
    await router.push(sub === "map" ? "/bureau/outils" : `/bureau/outils/${sub}`);
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
  it("shows the members map of the active season, filtered by group", async () => {
    const { byId, all, sent } = await render();
    expect(sent("GET", "/api/reports/map-points").map((c) => c.path)).toEqual(["/api/reports/map-points?season=2026-2027"]);
    await vi.waitFor(() => expect(byId("map-stats")!.textContent.trim()).toBe("3 adhérents répartis sur 2 adresses"));
    expect(byId("map-groups")!.textContent.trim()).toBe("🧗 Tous les groupes ▾");

    byId("map-groups")!.click();
    await flushPromises();
    expect(all("map-group").map((c) => (c as HTMLInputElement).value)).toEqual(["Compet", "Loisir"]);
    all("map-group")[1]!.click(); // Loisir hidden
    await flushPromises();
    expect(byId("map-stats")!.textContent.trim()).toBe("1 adhérent réparti sur 1 adresse (filtre : 1 groupe)");
    expect(byId("map-groups")!.textContent.trim()).toBe("🧗 1 groupe filtré ▾");
    expect(byId<HTMLInputElement>("map-group-all")!.indeterminate).toBe(true);

    byId("map-group-all")!.click(); // every group shown
    await flushPromises();
    expect(byId("map-stats")!.textContent.trim()).toBe("3 adhérents répartis sur 2 adresses");
    byId("map-group-all")!.click(); // none
    await flushPromises();
    expect(byId("map-stats")!.textContent.trim()).toBe("0 adhérent réparti sur 0 adresse (filtre : 0 groupe)");
    expect(byId("map-groups")!.textContent.trim()).toBe("⚠️ Aucun groupe sélectionné ▾");
  });

  it("shows the groups of the filter as text", async () => {
    const hostile = `<img src=x onerror="window.hacked=1"><b>`;
    const mapPoints = ANSWERS["GET /api/reports/map-points"]!;
    ANSWERS["GET /api/reports/map-points"] = () =>
      json({ season: "2026-2027", points: [{ address: "", lat: 45.8, lon: 5.05, members: [{ name: hostile, group: hostile }] }] });
    try {
      const { byId, all } = await render();
      await vi.waitFor(() => expect(byId("map-stats")).not.toBeNull());
      byId("map-groups")!.click();
      await flushPromises();
      const option = all("map-group")[0]!;
      expect((option as HTMLInputElement).value).toBe(hostile);
      expect(option.parentElement!.textContent.trim()).toBe(hostile);
      const popover = option.closest('[role="dialog"]');
      expect(popover).not.toBeNull();
      expect(popover!.querySelectorAll("img, b")).toHaveLength(0);
      expect(byId("map-groups")!.querySelectorAll("img, b")).toHaveLength(0);
      expect("hacked" in window).toBe(false);
    } finally {
      ANSWERS["GET /api/reports/map-points"] = mapPoints;
    }
  });

  it("reloads the map for another season, then keeps it while showing the pivot table", async () => {
    const { byId, open, sent } = await render();
    const season = byId<HTMLSelectElement>("map-season")!;
    expect([...season.options].map((o) => o.value)).toEqual(["2026-2027", "2025-2026", "Toutes les saisons"]);
    season.value = "Toutes les saisons";
    season.dispatchEvent(new Event("change"));
    await flushPromises();
    expect(sent("GET", "/api/reports/map-points").at(-1)!.path).toBe("/api/reports/map-points?season=Toutes%20les%20saisons");

    await open("pivot");
    expect(byId("sub-side-pivot")!.getAttribute("aria-current")).toBe("page");
    await vi.waitFor(() => expect(byId("pivot-table")).not.toBeNull());
    expect(sent("GET", "/api/reports/pivot-records").map((c) => c.path)).toEqual(["/api/reports/pivot-records?season=2026-2027"]);
    const pivotSeason = byId<HTMLSelectElement>("pivot-season")!;
    pivotSeason.value = "Toutes les saisons";
    pivotSeason.dispatchEvent(new Event("change"));
    await flushPromises();
    expect(sent("GET", "/api/reports/pivot-records").at(-1)!.path).toBe("/api/reports/pivot-records?season=Toutes%20les%20saisons");
    byId("tools-refresh")!.click();
    await flushPromises();
    expect(sent("GET", "/api/reports/pivot-records")).toHaveLength(3);
    expect(byId("toast")!.textContent).toBe("🔄 Tableau croisé dynamique réactualisé.");

    // The map stays loaded: back to it, no new request
    await open("map");
    expect(byId("sub-side-map")!.getAttribute("aria-current")).toBe("page");
    expect(sent("GET", "/api/reports/map-points")).toHaveLength(2);
    byId("tools-refresh")!.click();
    await flushPromises();
    expect(sent("GET", "/api/reports/map-points")).toHaveLength(3);
    expect(byId("toast")!.textContent).toBe("🔄 Carte réactualisée.");
  });

  it("says when the map or the pivot table fails", async () => {
    const mapPoints = ANSWERS["GET /api/reports/map-points"]!;
    const pivot = ANSWERS["GET /api/reports/pivot-records"]!;
    ANSWERS["GET /api/reports/map-points"] = () => json({ status: "error", message: "Erreur interne" }, 500);
    ANSWERS["GET /api/reports/pivot-records"] = () => json({ status: "error", message: "Erreur interne" }, 500);
    try {
      const { byId, open } = await render();
      await vi.waitFor(() => expect(byId("map-status")!.textContent).toContain("❌ Impossible de charger la carte"));
      expect(byId("map-stats")).toBeNull();
      await open("pivot");
      await vi.waitFor(() =>
        expect(byId("pivot-status")!.textContent.trim()).toBe("❌ Impossible de charger le tableau croisé dynamique : Erreur interne"),
      );
    } finally {
      ANSWERS["GET /api/reports/map-points"] = mapPoints;
      ANSWERS["GET /api/reports/pivot-records"] = pivot;
    }
  });

  it("opens the sub-page of the URL, titled with it; the import is for admins only", async () => {
    const admin = await render("admin", "/bureau/outils/ffme-import");
    expect(admin.byId("pane-ffme-import")).not.toBeNull();
    expect(admin.sent("GET", "/api/reports/map-points")).toHaveLength(0);
    expect(document.querySelector("h1")!.textContent).toBe("Import FFME");
    expect(document.title).toBe("Import FFME · Outils — ALJ Escalade");
    expect(admin.all("sub-side-ffme-import")).toHaveLength(1);
    admin.wrapper.unmount();
    document.body.innerHTML = "";

    const coach = await render("coach", "/bureau/outils/ffme-import");
    expect(coach.router.currentRoute.value.fullPath).toBe("/bureau/outils?reserve=ffme-import");
    expect(coach.byId("sub-side-ffme-import")).toBeNull();
    expect(coach.byId("pane-ffme-import")).toBeNull();
    expect(document.getElementById("refused-page")!.textContent).toContain("Import FFME est réservée aux administrateurs");
    expect(coach.byId("sub-side-map")!.getAttribute("aria-current")).toBe("page");
    expect(document.querySelector("h1")!.textContent).toBe("Outils");
  });

  it("previews the HelloAsso membership campaign: campaign, counters and rows per bucket", async () => {
    const { byId, all, sent } = await render("admin", "/bureau/outils/helloasso-import");
    expect(sent("POST", "/api/helloasso/memberships/preview")).toHaveLength(0);

    byId("ha-import-preview")!.click();
    await flushPromises();

    expect(sent("POST", "/api/helloasso/memberships/preview")).toHaveLength(1);
    expect(byId("ha-import-campaign")!.textContent).toContain("adhesion-escalade-2026-2027-amicale-laique-escalade-2");
    expect(byId("ha-import-campaign")!.textContent).toContain("2026-2027");
    expect(byId("ha-count-new")!.textContent).toContain("1");
    expect(byId("ha-count-blocked")!.textContent).toContain("1");
    expect(byId("ha-count-renewal")!.textContent).toContain("0");
    expect(all("ha-row-new").map((row) => row.textContent)).toEqual([expect.stringContaining("WEASLEY Ginny")]);
    expect(byId("ha-row-blocked")!.textContent).toContain("Date de naissance manquante ou illisible.");
    expect(all("ha-licence").map((cell) => cell.textContent)).toEqual(["—", "—"]);
    expect(all("ha-birth-date").map((cell) => cell.textContent)).toEqual(["11/08/2013", "—"]);
    expect(byId("ha-section-renewal")).toBeNull();
  });

  it("lists the club's membership campaigns, the active one selected, and previews and imports the one picked for this sync", async () => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const { byId, sent } = await render("admin", "/bureau/outils/helloasso-import");
    const select = byId<HTMLSelectElement>("ha-import-campaign-select")!;
    expect(select.value).toBe("adhesion-escalade-2026-2027-amicale-laique-escalade-2");
    expect([...select.options].map((option) => option.textContent.trim())).toEqual([
      "Adhésions 2026-2027 (campagne active)",
      "Adhésions de janvier (brouillon)",
    ]);
    byId("ha-import-preview")!.click();
    await flushPromises();
    expect(byId("ha-import-result")).not.toBeNull();

    select.value = "adhesions-bis-2026-2027";
    select.dispatchEvent(new Event("change"));
    await flushPromises();
    expect(byId("ha-import-result")).toBeNull();
    byId("ha-import-preview")!.click();
    await flushPromises();
    byId("ha-import-apply")!.click();
    await flushPromises();

    expect(sent("POST", "/api/helloasso/memberships/preview").map((call) => call.body)).toEqual([
      { campaign: "adhesion-escalade-2026-2027-amicale-laique-escalade-2" },
      { campaign: "adhesions-bis-2026-2027" },
    ]);
    expect(sent("POST", "/api/helloasso/memberships/import").at(-1)!.body).toMatchObject({ campaign: "adhesions-bis-2026-2027" });
  });

  it("previews the active HelloAsso campaign when the campaign list can't be read", async () => {
    const campaigns = ANSWERS["GET /api/helloasso/campaigns"]!;
    ANSWERS["GET /api/helloasso/campaigns"] = () => json({ code: "storage_unavailable", message: "Firestore injoignable" }, 503);
    try {
      const { byId, sent } = await render("admin", "/bureau/outils/helloasso-import");
      expect(byId("ha-import-campaign-select")).toBeNull();
      byId("ha-import-preview")!.click();
      await flushPromises();
      expect(sent("POST", "/api/helloasso/memberships/preview").at(-1)!.body).toEqual({ campaign: null });
    } finally {
      ANSWERS["GET /api/helloasso/campaigns"] = campaigns;
    }
  });

  it("shows the FFME licence given on HelloAsso", async () => {
    const preview = ANSWERS["POST /api/helloasso/memberships/preview"]!;
    const licensed = { ...MEMBERSHIP_PREVIEW.rows[0]!, licence: "123456" };
    ANSWERS["POST /api/helloasso/memberships/preview"] = () => json({ ...MEMBERSHIP_PREVIEW, rows: [licensed] });
    try {
      const { byId } = await render("admin", "/bureau/outils/helloasso-import");
      byId("ha-import-preview")!.click();
      await flushPromises();

      expect(byId("ha-row-new")!.querySelector("[data-testid=ha-licence]")!.textContent).toBe("123456");
    } finally {
      ANSWERS["POST /api/helloasso/memberships/preview"] = preview;
    }
  });

  it("shows when each HelloAsso registration was made, the latest first", async () => {
    const earlier = {
      ...MEMBERSHIP_PREVIEW.rows[0]!,
      item_id: 3,
      first_name: "Ron",
      order_date: "2026-08-20T09:00:00+02:00",
      payment_date: "",
    };
    const later = {
      ...MEMBERSHIP_PREVIEW.rows[0]!,
      item_id: 4,
      first_name: "Fred",
      order_date: "2026-09-12T18:30:00+02:00",
      payment_date: "2026-09-15T08:00:00+02:00",
    };
    const preview = ANSWERS["POST /api/helloasso/memberships/preview"]!;
    ANSWERS["POST /api/helloasso/memberships/preview"] = () => json({ ...MEMBERSHIP_PREVIEW, rows: [earlier, later] });
    try {
      const { byId, all } = await render("admin", "/bureau/outils/helloasso-import");
      byId("ha-import-preview")!.click();
      await flushPromises();

      expect(all("ha-row-new").map((row) => row.querySelector("[data-testid=ha-order-date]")?.textContent)).toEqual([
        "12/09/2026",
        "20/08/2026",
      ]);
      expect(all("ha-row-new").map((row) => row.querySelector("[data-testid=ha-payment-date]")?.textContent)).toEqual(["15/09/2026", "—"]);
      expect(all("ha-row-new")[0]!.textContent).toContain("WEASLEY Fred");
    } finally {
      ANSWERS["POST /api/helloasso/memberships/preview"] = preview;
    }
  });

  it("imports the checked HelloAsso rows once confirmed, then lists the created members with a link to their record", async () => {
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValue(false);
    const { byId, all, sent } = await render("admin", "/bureau/outils/helloasso-import");
    byId("ha-import-preview")!.click();
    await flushPromises();
    const [checkbox] = all("ha-check").map((box) => box as HTMLInputElement);
    expect(checkbox!.checked).toBe(true);

    byId("ha-import-apply")!.click();
    await flushPromises();
    expect(confirm).toHaveBeenCalledOnce();
    expect(sent("POST", "/api/helloasso/memberships/import")).toHaveLength(0);

    confirm.mockResolvedValue(true);
    byId("ha-import-apply")!.click();
    await flushPromises();
    expect(sent("POST", "/api/helloasso/memberships/import").at(-1)!.body).toEqual({
      season: "2026-2027",
      campaign: "adhesion-escalade-2026-2027-amicale-laique-escalade-2",
      decisions: { 1: { bucket: "new", choice: "import" } },
    });
    expect(byId("ha-import-done")!.textContent).toContain("1 adhérent créé");
    const link = byId<HTMLAnchorElement>("ha-created")!.querySelector("a")!;
    expect(link.textContent).toContain("WEASLEY Ginny");
    expect(link.getAttribute("href")).toBe("/bureau/adherents?id=7&saison=2026-2027&achat=12");
    expect(byId("ha-import-done")!.textContent).toContain("1 renouvellement");
    const renewed = byId<HTMLAnchorElement>("ha-renewed")!.querySelector("a")!;
    expect(renewed.textContent).toContain("GRANGER Hermione");
    expect(renewed.getAttribute("href")).toBe("/bureau/adherents?id=4&saison=2026-2027&achat=13");
    expect(byId("ha-import-result")).toBeNull();
  });

  it("asks for a choice on each HelloAsso row to review, skipped by default", async () => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const preview = ANSWERS["POST /api/helloasso/memberships/preview"]!;
    ANSWERS["POST /api/helloasso/memberships/preview"] = () =>
      json({
        ...MEMBERSHIP_PREVIEW,
        rows: [...MEMBERSHIP_PREVIEW.rows, REVIEW_ROW],
        counts: { ...MEMBERSHIP_PREVIEW.counts, to_review: 1 },
      });
    try {
      const { byId, sent } = await render("admin", "/bureau/outils/helloasso-import");
      byId("ha-import-preview")!.click();
      await flushPromises();
      const select = byId<HTMLSelectElement>("ha-review-choice")!;
      expect(select.value).toBe("skip");
      expect([...select.options].map((option) => option.textContent.trim())).toEqual([
        "— Ignorer cette inscription —",
        "Rattacher à GRANGER Hermione (né(e) le 19/09/2012, licence 123456)",
        "Créer un nouvel adhérent",
      ]);
      expect(byId("ha-row-to_review")!.textContent).toContain("date de naissance différente");

      select.value = "link:4";
      select.dispatchEvent(new Event("change"));
      await flushPromises();
      expect(byId("ha-import-selected")!.textContent).toContain("2");
      byId("ha-import-apply")!.click();
      await flushPromises();
      expect(sent("POST", "/api/helloasso/memberships/import").at(-1)!.body).toEqual({
        season: "2026-2027",
        campaign: "adhesion-escalade-2026-2027-amicale-laique-escalade-2",
        decisions: { 1: { bucket: "new", choice: "import" }, 3: { bucket: "to_review", choice: "link:4" } },
      });
    } finally {
      ANSWERS["POST /api/helloasso/memberships/preview"] = preview;
    }
  });

  it("shows the changes made on HelloAsso, and asks before overwriting a value also changed in the CRM", async () => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const preview = ANSWERS["POST /api/helloasso/memberships/preview"]!;
    const changed = {
      ...MEMBERSHIP_PREVIEW.rows[0]!,
      item_id: 4,
      bucket: "updated",
      status: "Refunded",
      refund_date: "2026-10-14T09:30:00+02:00",
      changes: [{ field: "status", crm: "Processed", before: "Processed", after: "Refunded" }],
    };
    const conflict = {
      ...MEMBERSHIP_PREVIEW.rows[0]!,
      item_id: 5,
      bucket: "to_review",
      last_name: "LOVEGOOD",
      changes: [{ field: "amount", crm: "120.00", before: "150.00", after: "0.00" }],
    };
    ANSWERS["POST /api/helloasso/memberships/preview"] = () => json({ ...MEMBERSHIP_PREVIEW, rows: [changed, conflict] });
    try {
      const { byId, all, sent } = await render("admin", "/bureau/outils/helloasso-import");
      byId("ha-import-preview")!.click();
      await flushPromises();
      expect(byId("ha-row-updated")!.textContent).toContain("Statut : Processed → Refunded");
      expect(byId("ha-refund-date")!.textContent).toBe("Remboursé le 14/10/2026");
      expect(byId("ha-row-to_review")!.textContent).toContain("Montant : CRM 120.00 · HelloAsso 0.00 (avant 150.00)");
      expect(byId("ha-review-choice")).toBeNull();
      const checks = all("ha-check").map((box) => box as HTMLInputElement);
      expect(checks.map((box) => box.checked)).toEqual([true, false]);

      checks[1]!.click();
      await flushPromises();
      byId("ha-import-apply")!.click();
      await flushPromises();
      expect(sent("POST", "/api/helloasso/memberships/import").at(-1)!.body).toEqual({
        season: "2026-2027",
        campaign: "adhesion-escalade-2026-2027-amicale-laique-escalade-2",
        decisions: { 4: { bucket: "updated", choice: "import" }, 5: { bucket: "to_review", choice: "import" } },
      });
    } finally {
      ANSWERS["POST /api/helloasso/memberships/preview"] = preview;
    }
  });

  it("shows when the HelloAsso import last ran and who ran it", async () => {
    const lastSync = ANSWERS["GET /api/helloasso/memberships/last-sync"]!;
    try {
      const first = await render("admin", "/bureau/outils/helloasso-import");
      expect(first.byId("ha-last-sync")!.textContent).toContain("Aucune synchronisation");
      first.wrapper.unmount();
      document.body.innerHTML = "";

      ANSWERS["GET /api/helloasso/memberships/last-sync"] = () =>
        json({
          last_sync: { at: "2026-10-31T09:15:00+00:00", author: "albus.dumbledore@alj-escalade.fr", season: "2026-2027", campaign: "x" },
        });
      const { byId } = await render("admin", "/bureau/outils/helloasso-import");
      expect(byId("ha-last-sync")!.textContent).toMatch(/Dernière synchro : 31\/10\/2026 \d\d:15, par albus.dumbledore@alj-escalade.fr/);
    } finally {
      ANSWERS["GET /api/helloasso/memberships/last-sync"] = lastSync;
    }
  });

  it("blocks the HelloAsso preview of a campaign of another season, with the reason", async () => {
    const preview = ANSWERS["POST /api/helloasso/memberships/preview"]!;
    const reason = "La campagne « adhesion-escalade-2025-2026 » ne correspond pas à la saison active 2026-2027 : import bloqué.";
    ANSWERS["POST /api/helloasso/memberships/preview"] = () => json({ ...MEMBERSHIP_PREVIEW, blocked_reason: reason });
    try {
      const { byId } = await render("admin", "/bureau/outils/helloasso-import");
      byId("ha-import-preview")!.click();
      await flushPromises();
      expect(byId("ha-import-blocked")!.textContent).toContain(reason);
    } finally {
      ANSWERS["POST /api/helloasso/memberships/preview"] = preview;
    }
  });

  it("shows the HelloAsso error on the card", async () => {
    const preview = ANSWERS["POST /api/helloasso/memberships/preview"]!;
    ANSWERS["POST /api/helloasso/memberships/preview"] = () =>
      json(
        {
          status: "error",
          message: "Identifiants de l'API HelloAsso non configurés sur le serveur.",
          code: "helloasso_credentials_missing",
        },
        502,
      );
    try {
      const { byId } = await render("admin", "/bureau/outils/helloasso-import");
      byId("ha-import-preview")!.click();
      await flushPromises();
      expect(byId("ha-import-error")!.textContent).toContain("Identifiants de l'API HelloAsso non configurés");
      expect(byId("ha-import-campaign")).toBeNull();
    } finally {
      ANSWERS["POST /api/helloasso/memberships/preview"] = preview;
    }
  });

  it("disables the HelloAsso import offline, with an explanation", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const { byId, sent } = await render("admin", "/bureau/outils/helloasso-import");
    expect(byId<HTMLButtonElement>("ha-import-preview")!.disabled).toBe(true);
    expect(byId("ha-import-offline")!.textContent).toContain("hors ligne");

    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    window.dispatchEvent(new Event("online"));
    await flushPromises();
    expect(byId<HTMLButtonElement>("ha-import-preview")!.disabled).toBe(false);
    expect(byId("ha-import-offline")).toBeNull();
    expect(sent("POST", "/api/helloasso/memberships/preview")).toHaveLength(0);
  });

  it("keeps the HelloAsso import away from coaches", async () => {
    const coach = await render("coach", "/bureau/outils/helloasso-import");
    expect(coach.router.currentRoute.value.fullPath).toBe("/bureau/outils?reserve=helloasso-import");
    expect(coach.byId("sub-side-helloasso-import")).toBeNull();
    expect(coach.byId("ha-import-preview")).toBeNull();
  });

  it("opens the former tab address on its sub-page", async () => {
    const { router, byId } = await render("coach", "/bureau/outils/ffme");
    expect(router.currentRoute.value.fullPath).toBe("/bureau/outils/ffme");
    expect(byId("pane-ffme")).not.toBeNull();
  });

  it("generates the attendance sheets", async () => {
    stubDownloads();
    const { byId, all, open, sent } = await render("coach", "/bureau/outils/presence");
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
    const { byId, sent } = await render("coach", "/bureau/outils/ffme");
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
    const { byId, all, sent } = await render("admin", "/bureau/outils/ffme-import");
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
    const { byId, sent } = await render("admin", "/bureau/outils/ffme-import");
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
