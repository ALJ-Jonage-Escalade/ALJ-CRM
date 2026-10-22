import { flushPromises, mount } from "@vue/test-utils";
import { IDBFactory } from "fake-indexeddb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { AUTH_KEY, type Auth, type AuthState } from "../composables/auth";
import { SIGN_IN_ERROR_KEY } from "../composables/signIn";
import { API_KEY, type ApiFetch } from "../lib/api";
import type { Role } from "../lib/roles";
import { createOfflineStore, STORE_KEY, type OfflineStore } from "../lib/store";
import CompetitionsPage from "./CompetitionsPage.vue";
import type { Competition } from "./competitions/competitions";

const USER = { uid: "u1", email: "coach@example.org" };
const COMPETITIONS: Competition[] = [
  {
    id: 10, nom: "Coupe du Rhône", date_competition: "2027-03-15", prix: 12, coaches: ["Alice"], statut: "en_preparation",
    participants: [
      { adherent_id: 1, nom: "MARTIN", prenom: "Léo", selectionne: true, statut_paiement: "paye", commande_helloasso: "CMD-1" },
      { adherent_id: 2, nom: "DURAND", prenom: "Zoé", selectionne: true, statut_paiement: "en_attente" },
      { adherent_id: 3, nom: "ABEL", prenom: "Max", selectionne: false, statut_paiement: "non_invite" },
    ],
  },
  { id: 9, nom: "Open passé", date_competition: "2025-01-10", statut: "close", participants: [] },
];
const CONTACTS = [{
  adherent_id: 2, last_name: "DURAND", first_name: "Zoé", phone: "06 22 22 22 22", creneau_groupe: "Compét. U14",
  emergency1_name: "Paul", emergency1_phone: "06 01 01 01 01", emergency2_name: "", emergency2_phone: "",
}];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ETag: `"${status}"` } });
}

function fakeApi(offline = false) {
  const calls: string[] = [];
  const api: ApiFetch = vi.fn(async (url: string) => {
    calls.push(url);
    if (offline) throw new TypeError("Failed to fetch");
    if (url === "/api/competitions") return json(COMPETITIONS);
    if (url === "/api/members/competitors") return json(CONTACTS);
    if (url === "/api/competition-members") return json([{ id: 1, tarif: "Compétition U18", creneau_groupe: "Compét. U18", phone: "x" }]);
    return json({}, 404);
  });
  return { api, calls };
}

async function render(state: AuthState, api: ApiFetch, store: OfflineStore, path = "/competitions") {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:any(.*)*", component: defineComponent({ render: () => null }) }] });
  await router.push(path);
  const auth: Auth = { state: ref(state), login: vi.fn(), logout: vi.fn(async () => {}), retry: vi.fn(async () => {}), stop: vi.fn() };
  const wrapper = mount(CompetitionsPage, {
    global: {
      plugins: [router],
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [STORE_KEY]: store, [SIGN_IN_ERROR_KEY]: ref(null) },
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  const all = (id: string) => wrapper.findAll(`[data-testid="${id}"]`);
  return { wrapper, byId, all, router };
}

async function settle(): Promise<void> {
  for (let i = 0; i < 5; i++) {
    await flushPromises();
    await new Promise((r) => setTimeout(r, 0));
  }
}

const signedIn = (role: Role): AuthState => ({ status: "signedIn", user: USER, role });

let store: OfflineStore;
beforeEach(() => {
  store = createOfflineStore({ indexedDB: new IDBFactory(), storage: localStorage });
});
afterEach(() => vi.restoreAllMocks());

describe("CompetitionsPage", () => {
  it("lists the competitions, archives apart", async () => {
    const { byId, all } = await render(signedIn("coach"), fakeApi().api, store);
    await settle();
    expect(all("comp-name").map((n) => n.text())).toEqual(["Coupe du Rhône"]);
    expect(byId("comp-count").text()).toBe("1 compétition · 1 archivée");
    expect(all("comp-card")[0]!.text()).toContain("2 participants · 1 en attente · 1 payé");
    await byId("toggle-archives").trigger("click");
    expect(byId("archived-list").text()).toContain("Open passé");
  });

  it("shows a competition's participants by group with payment status, contacts for coaches", async () => {
    const { byId, all } = await render(signedIn("coach"), fakeApi().api, store, "/competitions?id=10");
    await settle();
    expect(byId("detail-name").text()).toBe("Coupe du Rhône");
    expect([byId("kpi-selected").text(), byId("kpi-unpaid").text(), byId("kpi-paid").text()]).toEqual(["2", "1", "1"]);
    expect(all("participant-group").map((g) => g.find("h3").text())).toEqual(["Compét. U14 · 1 compétiteur", "Compét. U18 · 1 compétiteur", "Non identifiés · 1 compétiteur"]);
    expect(byId("emergency-link").attributes("href")).toBe("tel:0601010101");
    expect(byId("participant-card").text()).toContain("En attente");
    await byId("filter-unpaid").trigger("click");
    expect(all("participant-name").map((n) => n.text())).toEqual(["DURAND Zoé"]);
    expect(byId("manage-link").attributes("href")).toBe("/competitions/gestion");
  });

  it("shows a read-only account the competitions without contacts nor management", async () => {
    const { api, calls } = fakeApi();
    const { byId, wrapper } = await render(signedIn("readonly"), api, store, "/competitions?id=10");
    await settle();
    expect(byId("detail-name").text()).toBe("Coupe du Rhône");
    expect(calls).not.toContain("/api/members/competitors");
    expect(byId("emergency-link").exists()).toBe(false);
    expect(byId("manage-link").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("CMD-1");
  });

  it("refuses an account without a role", async () => {
    const { api, calls } = fakeApi();
    const { wrapper } = await render(signedIn(null), api, store);
    await settle();
    expect(wrapper.find("#gate").text()).toContain("Accès réservé");
    expect(calls.filter((c) => c !== "/api/auth/google/status")).toEqual([]);
  });

  it("shows offline the copy the former page kept", async () => {
    await store.start(USER.uid);
    await store.save("competitions", USER.uid, COMPETITIONS, null);  // no url: as web/shared/alj-store.js saves it
    await store.save("competitors", USER.uid, CONTACTS, null);
    const offline: AuthState = { status: "error", user: USER, message: "x", offline: true };
    const { byId, wrapper } = await render(offline, fakeApi(true).api, store, "/competitions?id=10");
    await settle();
    expect(byId("detail-name").text()).toBe("Coupe du Rhône");
    expect(byId("emergency-link").exists()).toBe(true);
    expect(wrapper.find("#sync-info").text()).toMatch(/^📴 Hors ligne — données du /);
  });
});
