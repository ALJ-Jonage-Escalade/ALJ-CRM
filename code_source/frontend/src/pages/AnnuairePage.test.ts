import { fakeAuth, json, settle } from "../test/harness";
import { mount } from "@vue/test-utils";
import { IDBFactory } from "fake-indexeddb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_KEY, type AuthState } from "../composables/auth";
import { API_KEY, type ApiFetch } from "../lib/api";
import { createOfflineStore, STORE_KEY, type OfflineStore } from "../lib/store";
import AnnuairePage from "./AnnuairePage.vue";
import type { MemberList } from "./adherents/members";
import { member } from "./adherents/members.fixture";

const USER = { uid: "u1", email: "coach@example.org" };
const CRENEAUX = [
  { groupe: "Loisir adultes", tarifs: ["Adulte loisir"], categorie_age: "", type: "" },
  { groupe: "Liste d'attente", tarifs: ["Attente"], categorie_age: "", type: "" },
];
const ACTIVE: MemberList = {
  season: "2026-2027",
  creneaux: CRENEAUX,
  members: [
    member({ user_id: 2, purchase_id: 12, last_name: "MARTIN", first_name: "Max", tarif_name: "Adulte loisir", status_norm: "Annulé" }),
    member({
      user_id: 1,
      purchase_id: 11,
      last_name: "DUPONT",
      first_name: "Léa",
      tarif_name: "Adulte loisir",
      status_norm: "Validé",
      phone: "+33 6 12 34 56 78",
      emergency_contacts: [{ name: "Paul", phone: "06 00 00 00 01" }],
      health_commitment: "Oui",
    }),
    member({ user_id: 3, purchase_id: 13, last_name: "PETIT", first_name: "Zoé", tarif_name: "Attente", status_norm: "Validé" }),
  ],
};

/** The API, or no network at all (offline). */
function fakeApi(offline = false) {
  const calls: string[] = [];
  const api: ApiFetch = vi.fn(async (url: string) => {
    calls.push(url);
    if (offline) {
      throw new TypeError("Failed to fetch");
    }
    if (url === "/api/seasons") {
      return json({ seasons: ["2026-2027", "2025-2026"], active: "2026-2027" }, 200, '"s1"');
    }
    if (url.startsWith("/api/members")) {
      return json(ACTIVE, 200, '"m1"');
    }
    return json({}, 404);
  });
  return { api, calls };
}

function render(state: AuthState, api: ApiFetch, store: OfflineStore) {
  const auth = fakeAuth(state);
  const wrapper = mount(AnnuairePage, {
    global: {
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [STORE_KEY]: store },
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  const names = () => wrapper.findAll('[data-testid="directory-card"] b').map((b) => b.text());
  return { wrapper, byId, names, auth };
}

let store: OfflineStore;
beforeEach(() => {
  localStorage.clear();
  store = createOfflineStore({ indexedDB: new IDBFactory(), storage: localStorage });
});
afterEach(() => vi.restoreAllMocks());

const coach: AuthState = { status: "signedIn", user: USER, role: "coach" };

describe("AnnuairePage", () => {
  it("lists the season without the waiting list, sorted, with its counts", async () => {
    const { byId, names, wrapper } = render(coach, fakeApi().api, store);
    await settle();
    expect(names()).toEqual(["Léa DUPONT", "Max MARTIN"]);
    expect([byId("kpi-shown").text(), byId("kpi-season").text(), byId("kpi-cancelled").text()]).toEqual(["2", "2", "1"]);
    expect(byId("directory-count").text()).toBe("2 adhérents affichés · saison 2026-2027");
    expect(wrapper.find('a[href="tel:+33612345678"]').exists()).toBe(true);
    expect(wrapper.find("#sync-info").text()).toBe("");
  });

  it("unfolds a card on demand, without health data", async () => {
    const { byId, wrapper } = render(coach, fakeApi().api, store);
    await settle();
    expect(byId("card-details").exists()).toBe(false);
    await byId("card-toggle").trigger("click");
    expect(byId("card-details").text()).toContain("Paul · 06 00 00 00 01");
    expect(wrapper.text()).not.toContain("Santé");
  });

  it("filters by search, status and slots, and remembers the filters without the search", async () => {
    const { byId, names } = render(coach, fakeApi().api, store);
    await settle();
    await byId("directory-search").setValue("mart");
    expect(names()).toEqual(["Max MARTIN"]);
    await byId("directory-search").setValue("");
    await byId("status-Validé").trigger("click");
    expect(names()).toEqual(["Léa DUPONT"]);
    await byId("filter-none").trigger("click");
    expect(byId("kpi-shown").text()).toBe("0");
    await byId("filter-all").trigger("click");
    await byId("status-all").trigger("click");
    expect(names()).toEqual(["Léa DUPONT", "Max MARTIN", "Zoé PETIT"]);
    const saved = JSON.parse(localStorage.getItem("alj_annuaire_filters")!);
    expect(saved).toMatchObject({ status: "", search: "", groups: { "Loisir adultes": true, "Liste d'attente": true } });
  });

  it("finds a member's emergency contacts from 2 letters", async () => {
    const { byId, wrapper } = render(coach, fakeApi().api, store);
    await settle();
    await byId("tab-urgency").trigger("click");
    expect(byId("urgency-count").text()).toContain("au moins 2 lettres");
    await byId("urgency-search").setValue("du");
    expect(wrapper.findAll('[data-testid="urgency-card"]')).toHaveLength(1);
    expect(byId("urgency-card").text()).toContain("Urgence 1");
    expect(byId("urgency-card").find('a[href="tel:0600000001"]').exists()).toBe(true);
  });

  it("keeps the list on the device and shows it offline, with its date", async () => {
    const first = render(coach, fakeApi().api, store);
    await settle();
    first.wrapper.unmount();
    const saved = await store.load<{ members: object[] }>("directory", USER.uid);
    expect(saved?.data.members).toHaveLength(3);
    expect(saved?.data.members[0]).not.toHaveProperty("health_commitment");

    // Next visit without network: the role cannot be checked, the copy is shown
    const offline: AuthState = { status: "error", user: USER, message: "Serveur injoignable", offline: true };
    const { names, wrapper } = render(offline, fakeApi(true).api, store);
    await settle();
    expect(names()).toEqual(["Léa DUPONT", "Max MARTIN"]);
    expect(wrapper.find("#offline-notice").exists()).toBe(true);
    expect(wrapper.find("#sync-info").text()).toMatch(/^📴 Hors ligne — données du \d{2}\/\d{2}\/\d{4}/);
  });

  it("shows nothing offline for another user", async () => {
    render(coach, fakeApi().api, store);
    await settle();
    const other: AuthState = { status: "error", user: { uid: "u2", email: "x@example.org" }, message: "x", offline: true };
    const { names, byId } = render(other, fakeApi(true).api, store);
    await settle();
    expect(names()).toEqual([]);
    expect(byId("directory-count").text()).toBe("Aucune donnée de l'annuaire sur cet appareil.");
  });

  it.each(["readonly", null] as const)("asks nothing for %s and reads nothing from the device", async (role) => {
    const { api, calls } = fakeApi();
    const load = vi.spyOn(store, "load");
    const { wrapper } = render({ status: "signedIn", user: USER, role }, api, store);
    await settle();
    expect(calls.filter((c) => c !== "/api/auth/google/status")).toEqual([]);
    expect(load).not.toHaveBeenCalled();
    expect(wrapper.find("#gate").text()).toContain("Accès réservé");
  });

  it("wipes the device's copy when the server refuses the list (403)", async () => {
    render(coach, fakeApi().api, store);
    await settle();
    const refusing: ApiFetch = vi.fn(async (url: string) =>
      url.startsWith("/api/members") ? json({ status: "error" }, 403) : json({ seasons: [], active: "" }),
    );
    const { wrapper } = render(coach, refusing, store);
    await settle();
    expect(await store.load("directory", USER.uid)).toBeNull();
    expect(wrapper.find("#sync-info").text()).toBe("🔒 Accès réservé aux coachs");
  });
});
