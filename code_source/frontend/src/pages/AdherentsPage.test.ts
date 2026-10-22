import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { AUTH_KEY, type Auth } from "../composables/auth";
import { API_KEY, type ApiFetch } from "../lib/api";
import { CLIENT_KEY, createApiClient } from "../lib/client";
import type { Role } from "../lib/roles";
import AdherentsPage from "./AdherentsPage.vue";
import { FILTER_KEY, type MemberList } from "./adherents/members";
import { member } from "./adherents/members.fixture";

function json(body: unknown, status = 200, etag?: string): Response {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (etag) headers.ETag = etag;
  return new Response(JSON.stringify(body), { status, headers });
}

const CRENEAUX = [
  { groupe: "Loisir adultes", tarifs: ["Adulte loisir"], categorie_age: "", type: "" },
  { groupe: "Liste d'attente", tarifs: ["Attente"], categorie_age: "", type: "" },
];
const ACTIVE: MemberList = {
  season: "2026-2027",
  creneaux: CRENEAUX,
  members: [
    member({ user_id: 1, purchase_id: 11, last_name: "DUPONT", first_name: "Léa", tarif_name: "Adulte loisir", status_norm: "Validé", phone: "+33 6 12 34 56 78", email_primary: "lea@example.org" }),
    member({ user_id: 2, purchase_id: 12, last_name: "MARTIN", first_name: "Max", tarif_name: "Adulte loisir", status_norm: "En cours", badge_rouge: "Oui" }),
    member({ user_id: 3, purchase_id: 13, last_name: "PETIT", first_name: "Zoé", tarif_name: "Attente", status_norm: "Validé" }),
  ],
};
const PAST: MemberList = { season: "2025-2026", creneaux: CRENEAUX, members: [member({ user_id: 4, purchase_id: 21, last_name: "ANCIEN", season_name: "2025-2026", tarif_name: "Adulte loisir" })] };

type Answer = (req: { search: string; ifNoneMatch: string | null }) => Response;
const ANSWERS: Record<string, Answer> = {
  "GET /api/seasons": () => json({ seasons: ["2026-2027", "2025-2026"], active: "2026-2027" }, 200, '"s1"'),
  "GET /api/members": ({ search, ifNoneMatch }) => {
    if (search.includes("1999")) return json({ status: "error", message: "Saison inconnue", code: "not_found" }, 404);
    if (search.includes("2025-2026")) return json(PAST, 200, '"m-past"');
    if (ifNoneMatch === '"m1"') return new Response(null, { status: 304 });
    return json(ACTIVE, 200, '"m1"');
  },
  "POST /api/cloud-db/sync": () => json({ status: "success", message: "ok", result: { pulled: 1, pushed: 0, full: true } }),
};

function render(role: Role = "admin", answers: Record<string, Answer> = ANSWERS) {
  const calls: { method: string; path: string; ifNoneMatch: string | null }[] = [];
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url, "http://alj.test");
    const method = init?.method ?? "GET";
    const ifNoneMatch = new Headers(init?.headers).get("If-None-Match");
    calls.push({ method, path: u.pathname + u.search, ifNoneMatch });
    const answer = answers[`${method} ${u.pathname}`];
    return answer ? answer({ search: u.search, ifNoneMatch }) : json({}, 404);
  });
  const auth: Auth = {
    state: ref({ status: "signedIn", user: { uid: "u1", email: "u@alj.example" }, role }),
    login: vi.fn(), logout: vi.fn(async () => {}), retry: vi.fn(async () => {}), stop: vi.fn(),
  };
  const wrapper = mount(AdherentsPage, {
    attachTo: document.body,
    global: {
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") },
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  const names = () => wrapper.findAll('[data-testid="data-row"]').map((tr) => tr.find("td").text());
  return { wrapper, calls, byId, names };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("AdherentsPage", () => {
  it("lists the active season without the waiting list, with links to the member record", async () => {
    const { byId, names, wrapper } = render();
    await flushPromises();
    expect(names()).toEqual(["DUPONT", "MARTIN"]);
    expect(byId("member-count").text()).toBe("2 adhérents affichés sur 3 (saison 2026-2027)");
    expect(byId("member-record").attributes("href")).toBe("/bureau/adherents-fiche?id=1&saison=2026-2027");
    expect(wrapper.find('a[href="tel:+33612345678"]').exists()).toBe(true);
    expect((byId("season-select").element as HTMLSelectElement).value).toBe("2026-2027");
    expect(byId("season-select").text()).toContain("2026-2027 (active)");
    expect(wrapper.find("#sync-info").text()).toMatch(/^☁️ À jour — /);
    expect(byId("member-add").attributes("href")).toBe("/bureau/adherents-fiche?ajout=1");
  });

  it("polls every 20 s with the ETag: unchanged polls are 304", async () => {
    vi.useFakeTimers();
    const { calls, names } = render();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(20_000);
    const polls = calls.filter((c) => c.path === "/api/members");
    expect(polls).toHaveLength(2);
    expect(polls[1]!.ifNoneMatch).toBe('"m1"');
    expect(names()).toEqual(["DUPONT", "MARTIN"]);
  });

  it("filters by search, status and slot, and remembers the filters but not the search", async () => {
    const { byId, names, wrapper } = render();
    await flushPromises();
    await byId("member-search").setValue("léa");
    expect(names()).toEqual(["DUPONT"]);
    await byId("member-search").setValue("");

    await byId("status-En cours").trigger("click");
    expect(names()).toEqual(["MARTIN"]);
    await byId("status-all").trigger("click");

    await byId("filter-toggle").trigger("click");
    const groups = wrapper.findAll('[data-testid="filter-group"]');
    expect(groups.map((g) => g.text())).toEqual(["Liste d'attente1", "Loisir adultes2"]);
    expect(groups.map((g) => (g.find("input").element as HTMLInputElement).checked)).toEqual([false, true]);
    await groups[0]!.find("input").setValue(true);
    expect(names()).toEqual(["DUPONT", "MARTIN", "PETIT"]);
    await byId("filter-none").trigger("click");
    expect(wrapper.find('[data-testid="data-empty"]').text()).toBe("Aucun adhérent ne correspond aux filtres actifs.");

    await byId("member-search").setValue("dupont");
    const saved = JSON.parse(localStorage.getItem(FILTER_KEY)!);
    expect(saved.groups).toEqual({ "Liste d'attente": false, "Loisir adultes": false });
    expect(saved.search).toBe("");
  });

  it("sorts by a column", async () => {
    const { byId, names } = render();
    await flushPromises();
    await byId("sort-last_name").trigger("click");
    expect(names()).toEqual(["MARTIN", "DUPONT"]);
    await byId("sort-diplome").trigger("click");  // the red badge first
    expect(names()).toEqual(["MARTIN", "DUPONT"]);
  });

  it("switches season, and falls back to the active season when the remembered one is gone", async () => {
    const { byId, names, calls } = render();
    await flushPromises();
    await byId("season-select").setValue("2025-2026");
    await flushPromises();
    expect(names()).toEqual(["ANCIEN"]);
    expect(byId("member-count").text()).toContain("(saison 2025-2026)");
    expect(calls.map((c) => c.path)).toContain("/api/members?season=2025-2026");

    localStorage.setItem(FILTER_KEY, JSON.stringify({ season: "1999-2000" }));
    const again = render();
    await flushPromises();
    expect(again.names()).toEqual(["DUPONT", "MARTIN"]);
  });

  it("exports the list shown to CSV, in the table's order", async () => {
    const saved: Blob[] = [];
    vi.spyOn(URL, "createObjectURL").mockImplementation((b) => {
      saved.push(b as Blob);
      return "blob:x";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { byId } = render();
    await flushPromises();
    await byId("sort-last_name").trigger("click");
    await byId("export-csv").trigger("click");
    const text = await saved[0]!.text();
    const lines = text.replace(/^﻿/, "").split("\r\n");
    expect(lines).toHaveLength(3);
    expect(lines[1]).toMatch(/^"MARTIN";"Max"/);
    // A phone number starting with + is kept as is (lib/csv.ts)
    expect(lines[2]).toContain('"+33 6 12 34 56 78"');
  });

  it("synchronises the database, then reloads the list", async () => {
    const { byId, calls, wrapper } = render("coach");
    await flushPromises();
    await byId("sync-now").trigger("click");
    await flushPromises();
    expect(calls).toContainEqual(expect.objectContaining({ method: "POST", path: "/api/cloud-db/sync?force=true" }));
    expect(calls.filter((c) => c.path === "/api/members")).toHaveLength(2);
    expect(wrapper.find("#toast").text()).toContain("synchronisée");
  });

  it("shows a coach no admin action", async () => {
    const { byId, wrapper } = render("coach");
    await flushPromises();
    expect(byId("member-add").exists()).toBe(false);
    expect(wrapper.find('a[href="/bureau/outils?tab=ffme-import"]').exists()).toBe(false);
    expect(wrapper.find('a[href="/bureau/outils?tab=ffme"]').exists()).toBe(true);
  });
});
