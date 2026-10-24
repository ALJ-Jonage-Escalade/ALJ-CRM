import { flushPromises, mount } from "@vue/test-utils";
import { IDBFactory } from "fake-indexeddb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { AUTH_KEY, type Auth, type AuthState } from "../composables/auth";
import { SIGN_IN_ERROR_KEY } from "../composables/signIn";
import { API_KEY, type ApiFetch } from "../lib/api";
import { CLIENT_KEY, createApiClient } from "../lib/client";
import type { Role } from "../lib/roles";
import { createOfflineStore, STORE_KEY, type OfflineStore } from "../lib/store";
import CompetitionsPage from "./CompetitionsPage.vue";
import type { Competition } from "./competitions/competitions";

const USER = { uid: "u1", email: "coach@example.org" };
const LEO = {
  adherent_id: 1,
  nom: "MARTIN",
  prenom: "Léo",
  selectionne: true,
  statut_paiement: "paye",
  montant_paye: 12,
  commande_helloasso: "CMD-1",
  updated_at: "t1",
};
const ZOE = { adherent_id: 2, nom: "DURAND", prenom: "Zoé", selectionne: true, statut_paiement: "en_attente", updated_at: "t2" };
const MAX = { adherent_id: 3, nom: "ABEL", prenom: "Max", selectionne: false, statut_paiement: "non_invite", updated_at: "t3" };
const COMPETITIONS: Competition[] = [
  {
    id: 10,
    nom: "Coupe du Rhône",
    date_competition: "2027-03-15",
    prix: 12,
    coaches: ["Alice"],
    statut: "en_preparation",
    participants: [LEO, ZOE, MAX],
  },
  { id: 9, nom: "Open passé", date_competition: "2025-01-10", statut: "close", participants: [] },
];
const CONTACTS = [
  {
    adherent_id: 2,
    last_name: "DURAND",
    first_name: "Zoé",
    phone: "06 22 22 22 22",
    creneau_groupe: "Compét. U14",
    emergency1_name: "Paul",
    emergency1_phone: "06 01 01 01 01",
    emergency2_name: "",
    emergency2_phone: "",
  },
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ETag: `"${status}-${JSON.stringify(body).length}"` },
  });
}

/** The server: the competitions as they change, writes recorded; `down` makes every call fail like a lost network. */
function fakeApi(options: { down?: boolean; patch?: (body: Record<string, unknown>) => Response | null } = {}) {
  const calls: { method: string; path: string; body?: Record<string, unknown> }[] = [];
  let competitions = structuredClone(COMPETITIONS);
  const state = { down: !!options.down };
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, "http://alj.test").pathname;
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" && init.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, path, body });
    if (state.down) throw new TypeError("Failed to fetch");
    if (method === "GET" && path === "/api/competitions") return json(competitions);
    if (path === "/api/members/competitors") return json(CONTACTS);
    if (path === "/api/competition-members")
      return json([
        { id: 1, nom: "MARTIN", prenom: "Léo", tarif: "Compétition U18", creneau_groupe: "Compét. U18", phone: "x" },
        { id: 4, nom: "NOUVEAU", prenom: "Ali" },
      ]);
    if (path === "/api/coaches") return json([{ id: 1, nom: "Alice" }]);
    const participant = /^\/api\/competitions\/10\/participants\/(\d+)$/.exec(path);
    if (method === "PATCH" && participant) {
      const refused = options.patch?.(body);
      if (refused) return refused;
      competitions = competitions.map((c) =>
        c.id !== 10
          ? c
          : {
              ...c,
              participants: c.participants!.map((p) =>
                p.adherent_id === Number(participant[1])
                  ? { ...p, ...body, unchanged_since: undefined, updated_at: `${p.updated_at}+` }
                  : p,
              ),
            },
      );
      return json(competitions[0]);
    }
    return json({}, 404);
  });
  return { api, calls, writes: () => calls.filter((c) => c.method !== "GET"), state };
}

async function render(state: AuthState, api: ApiFetch, store: OfflineStore, path = "/competitions") {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/:any(.*)*", component: defineComponent({ render: () => null }) }],
  });
  await router.push(path);
  const auth: Auth = { state: ref(state), login: vi.fn(), logout: vi.fn(async () => {}), retry: vi.fn(async () => {}), stop: vi.fn() };
  const wrapper = mount(CompetitionsPage, {
    attachTo: document.body,
    global: {
      plugins: [router],
      provide: {
        [AUTH_KEY]: auth,
        [API_KEY]: api,
        [CLIENT_KEY]: createApiClient(api, "http://alj.test"),
        [STORE_KEY]: store,
        [SIGN_IN_ERROR_KEY]: ref(null),
      },
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  const all = (id: string) => wrapper.findAll(`[data-testid="${id}"]`);
  const card = (nom: string) => all("participant-card").find((c) => c.find('[data-testid="participant-name"]').text().startsWith(nom))!;
  // Dialogs are rendered at the end of <body>
  const inBody = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  return { wrapper, byId, all, card, inBody, router, auth };
}

async function settle(): Promise<void> {
  for (let i = 0; i < 6; i++) {
    await flushPromises();
    await new Promise((r) => setTimeout(r, 0));
  }
}

const signedIn = (role: Role): AuthState => ({ status: "signedIn", user: USER, role });
const offline: AuthState = { status: "error", user: USER, message: "x", offline: true };

let store: OfflineStore;
beforeEach(() => {
  store = createOfflineStore({ indexedDB: new IDBFactory(), storage: localStorage });
});
afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

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
    expect([byId("kpi-selected").text(), byId("kpi-unpaid").text(), byId("kpi-paid").text(), byId("kpi-present").text()]).toEqual([
      "2",
      "1",
      "1",
      "0 / 2",
    ]);
    expect(all("participant-group").map((g) => g.find("h3").text())).toEqual([
      "Compét. U14 · 1 compétiteur",
      "Compét. U18 · 1 compétiteur",
      "Non identifiés · 1 compétiteur",
    ]);
    expect(byId("emergency-link").attributes("href")).toBe("tel:0601010101");
    await byId("filter-unpaid").trigger("click");
    expect(all("participant-name").map((n) => n.text())).toEqual(["DURAND Zoé"]);
    await byId("filter-notInvited").trigger("click");
    expect(all("participant-name").map((n) => n.text())).toEqual(["ABEL Max"]);
  });

  it("offers each competitor the action their payment allows", async () => {
    const { card } = await render(signedIn("coach"), fakeApi().api, store, "/competitions?id=10");
    await settle();
    const actions = (nom: string) =>
      card(nom)
        .findAll('[data-testid="participant-actions"] [data-testid]')
        .map((a) => a.attributes("data-testid"));
    expect(actions("MARTIN")).toEqual(["withdraw"]); // paid: no removal
    expect(actions("DURAND")).toEqual(["remove", "manual-payment"]);
  });

  it("shows a read-only account the competitions without contacts nor changes", async () => {
    const { api, calls } = fakeApi();
    const { byId, wrapper } = await render(signedIn("readonly"), api, store, "/competitions?id=10");
    await settle();
    expect(byId("detail-name").text()).toBe("Coupe du Rhône");
    expect(calls.map((c) => c.path)).not.toContain("/api/members/competitors");
    expect(calls.map((c) => c.path)).not.toContain("/api/coaches");
    expect(byId("emergency-link").exists()).toBe(false);
    for (const id of ["participe-switch", "participant-actions", "detail-actions", "create-comp", "sections", "add-members"])
      expect(byId(id).exists(), id).toBe(false);
    expect(byId("participe").text()).toBe("✅ Participe");
    expect(wrapper.text()).not.toContain("CMD-1");
  });

  it("refuses an account without a role", async () => {
    const { api, calls } = fakeApi();
    const { wrapper } = await render(signedIn(null), api, store);
    await settle();
    expect(wrapper.find("#gate").text()).toContain("Accès réservé");
    expect(calls.filter((c) => c.path !== "/api/auth/google/status")).toEqual([]);
  });

  it("shows offline the copy the former page kept", async () => {
    await store.start(USER.uid);
    await store.save("competitions", USER.uid, COMPETITIONS, null); // no url: as web/shared/alj-store.js saves it
    await store.save("competitors", USER.uid, CONTACTS, null);
    const { byId, wrapper } = await render(offline, fakeApi({ down: true }).api, store, "/competitions?id=10");
    await settle();
    expect(byId("detail-name").text()).toBe("Coupe du Rhône");
    expect(byId("emergency-link").exists()).toBe(true);
    expect(wrapper.find("#sync-info").text()).toMatch(/^📴 Hors ligne — données du /);
  });

  it("switches « Participe » online at once", async () => {
    const server = fakeApi();
    const { card } = await render(signedIn("coach"), server.api, store, "/competitions?id=10");
    await settle();
    await card("ABEL").find('[data-testid="participe-switch"]').setValue(true);
    await settle();
    expect(server.writes()).toEqual([{ method: "PATCH", path: "/api/competitions/10/participants/3", body: { selectionne: true } }]);
    expect((card("ABEL").find('[data-testid="participe-switch"]').element as HTMLInputElement).checked).toBe(true);
  });

  it("asks what happens to the money before unselecting a competitor who paid", async () => {
    const server = fakeApi();
    const { card, inBody } = await render(signedIn("coach"), server.api, store, "/competitions?id=10");
    await settle();
    await card("MARTIN").find('[data-testid="participe-switch"]').setValue(false);
    await settle();
    expect(inBody("withdraw-text")!.textContent).toMatch(/a payé 12,00\s€/);
    expect(server.writes()).toEqual([]);
    expect((card("MARTIN").find('[data-testid="participe-switch"]').element as HTMLInputElement).checked).toBe(true);
  });

  it("queues a change made offline, shows it pending, and sends it when the network comes back", async () => {
    await store.start(USER.uid);
    await store.save("competitions", USER.uid, COMPETITIONS, null, "/api/competitions");
    await store.save("competitors", USER.uid, CONTACTS, null, "/api/members/competitors");
    const server = fakeApi({ down: true });
    const { card, wrapper, auth } = await render(offline, server.api, store, "/competitions?id=10");
    await settle();
    await card("ABEL").find('[data-testid="participe-switch"]').setValue(true);
    await settle();
    expect(card("ABEL").find('[data-testid="queued"]').exists()).toBe(true);
    expect((card("ABEL").find('[data-testid="participe-switch"]').element as HTMLInputElement).checked).toBe(true);
    expect(wrapper.find("#sync-info").text()).toContain("⏳ 1 modification à envoyer");
    expect((await store.queued(USER.uid)).map((e) => e.key)).toEqual(["10:3:selectionne"]);

    server.state.down = false; // back online
    (auth.state as { value: AuthState }).value = signedIn("coach");
    window.dispatchEvent(new Event("online"));
    await settle();
    expect(server.writes()).toEqual([
      { method: "PATCH", path: "/api/competitions/10/participants/3", body: { selectionne: true, unchanged_since: "t3" } },
    ]);
    expect(await store.queued(USER.uid)).toEqual([]);
    expect(card("ABEL").find('[data-testid="queued"]').exists()).toBe(false);
    expect(document.querySelector("#toast")!.textContent).toContain("Modifications faites hors ligne envoyées");
  });

  it("reports a change refused when sent, and drops it", async () => {
    await store.start(USER.uid);
    await store.queue(USER.uid, {
      key: "10:3:selectionne",
      uid: USER.uid,
      flag: "selectionne",
      value: true,
      url: "/api/competitions/10/participants/3",
      unchanged_since: "t0",
      label: "ABEL Max (Coupe du Rhône)",
      queuedAt: 1,
    });
    const server = fakeApi({ patch: () => json({ status: "error", message: "Modifié", code: "changed" }, 409) });
    await render(signedIn("coach"), server.api, store, "/competitions?id=10");
    await settle();
    expect(server.writes()).toHaveLength(1);
    expect(document.querySelector("#toast")!.textContent).toContain(
      "ABEL Max (Coupe du Rhône) : modifié entre-temps sur un autre appareil",
    );
    expect(await store.queued(USER.uid)).toEqual([]);
  });

  it("refuses other changes offline", async () => {
    await store.start(USER.uid);
    await store.save("competitions", USER.uid, COMPETITIONS, null, "/api/competitions");
    await store.save("competitors", USER.uid, CONTACTS, null, "/api/members/competitors");
    const server = fakeApi({ down: true });
    const { byId } = await render(offline, server.api, store, "/competitions?id=10");
    await settle();
    await byId("load-group").trigger("click");
    expect(document.querySelector("#toast")!.textContent).toContain("Hors ligne : seules les cases « Participe » et « Présent »");
    expect(server.writes()).toEqual([]);
  });
});
