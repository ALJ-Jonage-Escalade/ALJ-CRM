import { fakeAuth, json as jsonAnswer, settle } from "../test/harness";
import { flushPromises, mount, type DOMWrapper } from "@vue/test-utils";
import { IDBFactory } from "fake-indexeddb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { AUTH_KEY, type AuthState } from "../composables/auth";
import { WIDE_LAYOUT_QUERY } from "../composables/media";
import { API_KEY, type ApiFetch } from "../lib/api";
import { CLIENT_KEY, createApiClient } from "../lib/client";
import type { Role } from "../lib/roles";
import { createOfflineStore, STORE_KEY, type OfflineStore } from "../lib/store";
import { routes } from "../router";
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
const ZOE = {
  adherent_id: 2,
  nom: "DURAND",
  prenom: "Zoé",
  sex: "F" as const,
  selectionne: true,
  statut_paiement: "en_attente",
  updated_at: "t2",
};
const MAX = { adherent_id: 3, nom: "ABEL", prenom: "Max", selectionne: false, statut_paiement: "non_invite", updated_at: "t3" };
const COMPETITIONS: Competition[] = [
  {
    id: 10,
    nom: "Coupe du Rhône",
    date_competition: "2027-03-15",
    prix: 12,
    coaches: ["Alice"],
    coach_ids: [1],
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
    emergency_contacts: [{ name: "Paul", phone: "06 01 01 01 01" }],
    emergency1_name: "Paul",
    emergency1_phone: "06 01 01 01 01",
    emergency2_name: "",
    emergency2_phone: "",
  },
];

/** An answer with an ETag, as the server sends them (the polls send it back). */
function json(body: unknown, status = 200): Response {
  return jsonAnswer(body, status, `"${status}-${JSON.stringify(body).length}"`);
}

/** The server: the competitions as they change, writes recorded; `down` makes every call fail like a lost network. */
function fakeApi(options: { down?: boolean; patch?: (body: Record<string, unknown>) => Response | null } = {}) {
  const calls: { method: string; path: string; body?: Record<string, unknown> }[] = [];
  // The query string of each call, by path (calls keeps the path alone)
  const queries: { path: string; status: string[] }[] = [];
  let competitions = structuredClone(COMPETITIONS);
  const state = { down: !!options.down };
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const { pathname: path, searchParams } = new URL(url, "http://alj.test");
    queries.push({ path, status: searchParams.getAll("status") });
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" && init.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, path, body });
    if (state.down) {
      throw new TypeError("Failed to fetch");
    }
    if (method === "GET" && path === "/api/competitions") {
      return json(competitions);
    }
    if (path === "/api/members/competitors") {
      return json(CONTACTS);
    }
    if (path === "/api/competition-members") {
      return json([
        { id: 1, nom: "MARTIN", prenom: "Léo", tarif: "Compétition U18", creneau_groupe: "Compét. U18", phone: "x" },
        { id: 4, nom: "NOUVEAU", prenom: "Ali" },
      ]);
    }
    if (method === "POST" && path === "/api/competitions/10/participants") {
      competitions = competitions.map((c) =>
        c.id !== 10 ? c : { ...c, participants: [...c.participants!, { adherent_id: Number(body!.adherent_id), selectionne: true }] },
      );
      return json(competitions[0]);
    }
    if (method === "POST" && path === "/api/competitions/10/load-group") {
      return json({ added: 0, competition: competitions[0] });
    }
    if (path === "/api/coaches") {
      return json([{ id: 1, nom: "Alice" }]);
    }
    const participant = /^\/api\/competitions\/10\/participants\/(\d+)$/.exec(path);
    if (method === "PATCH" && participant) {
      const refused = options.patch?.(body);
      if (refused) {
        return refused;
      }
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
  return { api, calls, queries, writes: () => calls.filter((c) => c.method !== "GET"), state };
}

async function render(state: AuthState, api: ApiFetch, store: OfflineStore, path = "/competitions") {
  // The app's routes: the page renders its sub-pages (router.ts)
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push(path);
  const auth = fakeAuth(state);
  const wrapper = mount(RouterView, {
    attachTo: document.body,
    global: {
      plugins: [router],
      provide: {
        [AUTH_KEY]: auth,
        [API_KEY]: api,
        [CLIENT_KEY]: createApiClient(api, "http://alj.test"),
        [STORE_KEY]: store,
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

/** Opens the competition's « Plus » menu: Reka UI opens it on pointerdown or the keyboard, not on a bare click. */
async function openMore(byId: (id: string) => DOMWrapper<Element>): Promise<void> {
  byId("detail-more").element.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await flushPromises();
}

/** Types in an input rendered outside the wrapper (dialogs). */
async function search(input: HTMLElement, text: string): Promise<void> {
  (input as HTMLInputElement).value = text;
  input.dispatchEvent(new Event("input"));
  await flushPromises();
}

const signedIn = (role: Role): AuthState => ({ status: "signedIn", user: USER, role });
const offline: AuthState = { status: "error", user: USER, message: "x", offline: true };

let store: OfflineStore;
beforeEach(() => {
  store = createOfflineStore({ indexedDB: new IDBFactory(), storage: localStorage });
});
/** A computer screen (jsdom has no matchMedia: a phone otherwise); undone after each test. */
function onComputer(): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === WIDE_LAYOUT_QUERY,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
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
    onComputer();
    const { byId, all } = await render(signedIn("coach"), fakeApi().api, store, "/competitions?id=10");
    await settle();
    expect(byId("detail-name").text()).toBe("Coupe du Rhône");
    expect([byId("filter-selected").text(), byId("filter-unpaid").text()]).toEqual([
      "✅ Participe : Oui (2)",
      "⏳ Paiement en attente (1)",
    ]);
    expect(byId("kpi-selected").exists()).toBe(false);
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

  it("filters by slot group on a phone, where a competition day goes one group after the other", async () => {
    const { byId, all } = await render(signedIn("coach"), fakeApi().api, store, "/competitions?id=10");
    await settle();
    expect([byId("filter-selected").exists(), byId("participant-search").exists()]).toEqual([false, false]);
    expect(
      byId("group-filter")
        .findAll("option")
        .map((o) => o.text()),
    ).toEqual(["📋 Tous (3)", "Compét. U14 - F (1)", "Compét. U18 (1)"]);
    await byId("group-filter").setValue("Compét. U18");
    expect(all("participant-name").map((n) => n.text())).toEqual(["MARTIN Léo"]);
    expect(byId("participant-count").text()).toBe("1 compétiteur en « Compét. U18 »");
    await byId("group-filter").setValue("");
    expect(all("participant-name")).toHaveLength(3);
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
    for (const id of [
      "participe-switch",
      "participant-actions",
      "detail-actions",
      "create-comp",
      "subnav-side",
      "subnav-strip",
      "detail-more",
    ]) {
      expect(byId(id).exists(), id).toBe(false);
    }
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

  it("offers and loads only the members at the competitor statuses", async () => {
    const server = fakeApi();
    const { byId, inBody } = await render(signedIn("coach"), server.api, store, "/competitions?id=10");
    await settle();
    expect(server.queries.filter((q) => q.path === "/api/competition-members").map((q) => q.status)).toContainEqual(["Terminé"]);
    expect(server.queries.filter((q) => q.path === "/api/competition-members" && !q.status.length)).toEqual([]);

    await byId("add-competitor-btn").trigger("click");
    await settle();
    expect(inBody("member-status-hint")!.textContent).toBe("Adhérents au statut « Terminé » uniquement");
    await search(inBody("member-search")!, "zzz");
    expect(inBody("add-competitor-dialog")!.textContent).toContain("seuls les adhérents au statut « Terminé » peuvent être ajoutés");

    await openMore(byId);
    inBody("load-group")!.click();
    await settle();
    expect(server.queries.filter((q) => q.path === "/api/competitions/10/load-group").map((q) => q.status)).toEqual([["Terminé"]]);
    expect(document.querySelector("#toast")!.textContent).toContain(
      "Tous les membres « Terminé » du groupe « Compétition » sont déjà présents dans la liste.",
    );
  });

  it("adds competitors one after the other from a single dialog", async () => {
    const server = fakeApi();
    const { byId, inBody, all } = await render(signedIn("coach"), server.api, store, "/competitions?id=10");
    await settle();
    expect(byId("toggle-add").exists()).toBe(false); // the dialog is the only way to add one competitor
    await byId("add-competitor-btn").trigger("click");
    await settle();
    await search(inBody("member-search")!, "nouv");
    expect(document.querySelectorAll('[data-testid="member-result"]')).toHaveLength(1);
    inBody("member-add")!.click();
    await settle();
    expect(server.writes()).toEqual([
      { method: "POST", path: "/api/competitions/10/participants", body: { adherent_id: 4, selectionne: true } },
    ]);
    // Still open, search cleared, for the next one
    expect(inBody("add-competitor-dialog")).not.toBeNull();
    expect((inBody("member-search") as HTMLInputElement).value).toBe("");
    expect(all("participant-card")).toHaveLength(4);
  });

  it("refuses other changes offline", async () => {
    await store.start(USER.uid);
    await store.save("competitions", USER.uid, COMPETITIONS, null, "/api/competitions");
    await store.save("competitors", USER.uid, CONTACTS, null, "/api/members/competitors");
    const server = fakeApi({ down: true });
    const { byId, inBody } = await render(offline, server.api, store, "/competitions?id=10");
    await settle();
    await openMore(byId);
    inBody("load-group")!.click();
    await flushPromises();
    expect(document.querySelector("#toast")!.textContent).toContain("Hors ligne : seules les cases « Participe » et « Présent »");
    expect(server.writes()).toEqual([]);
  });

  it("goes back to the cards when the competition already selected is opened from the table", async () => {
    const { byId, router } = await render(signedIn("coach"), fakeApi().api, store, "/competitions?id=10");
    await settle();
    await byId("view-table").trigger("click");
    expect(byId("comp-detail").exists()).toBe(false);
    await byId("comp-table-open").trigger("click");
    await settle();
    expect(router.currentRoute.value.query.id).toBe("10");
    expect(byId("view-cards").attributes("aria-pressed")).toBe("true");
    expect(byId("comp-detail").exists()).toBe(true);
  });

  it("creates a competition from the list and edits one from the table", async () => {
    const { byId } = await render(signedIn("coach"), fakeApi().api, store, "/bureau/competitions");
    await settle();
    await byId("create-comp").trigger("click");
    await settle();
    expect(document.querySelector('[data-testid="create-dialog"]')).not.toBeNull();
    document.querySelector<HTMLButtonElement>('[data-testid="create-dialog"] [aria-label="Fermer"]')!.click();
    await settle();
    await byId("view-table").trigger("click");
    await byId("edit-comp-row").trigger("click");
    await settle();
    expect(document.querySelector('[data-testid="edit-dialog"]')?.textContent).toContain("Modifier : Coupe du Rhône");
  });

  it("shows the selected competition's month on the calendar and opens a competition from it", async () => {
    const { byId, all, router } = await render(signedIn("coach"), fakeApi().api, store, "/competitions?id=10");
    await settle();
    await byId("view-calendar").trigger("click");
    expect(byId("calendar-title").text()).toBe("Mars 2027");
    expect(byId("when-upcoming").exists()).toBe(false);
    expect(byId("comp-season-filter").exists()).toBe(false);
    expect(all("calendar-comp-chip").map((c) => c.text())).toEqual(["Coupe du Rhône"]);
    await router.push("/competitions");
    await all("calendar-comp-chip")[0]!.trigger("click");
    await settle();
    expect(router.currentRoute.value.query.id).toBe("10");
    expect(byId("view-cards").attributes("aria-pressed")).toBe("true");
    expect(byId("comp-detail").exists()).toBe(true);
  });

  it("keeps the archived competitions on the calendar, and applies the search", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2025, 0, 5));
    try {
      const { byId, all } = await render(signedIn("coach"), fakeApi().api, store);
      await settle();
      await byId("view-calendar").trigger("click");
      expect(byId("calendar-title").text()).toBe("Janvier 2025");
      expect(all("calendar-comp-chip").map((c) => c.text())).toEqual(["Open passé"]);
      await byId("comp-search").setValue("Rhône");
      expect(all("calendar-comp-chip")).toHaveLength(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("opens the first competition of the list by itself when the list and the detail are side by side", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === WIDE_LAYOUT_QUERY,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    try {
      const { byId, router } = await render(signedIn("coach"), fakeApi().api, store, "/competitions");
      await settle();
      expect(router.currentRoute.value.query.id).toBe("10");
      expect(byId("detail-name").text()).toBe("Coupe du Rhône");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("opens no competition by itself on a phone, where the detail would hide the list", async () => {
    const { byId, router } = await render(signedIn("coach"), fakeApi().api, store, "/competitions");
    await settle();
    expect(router.currentRoute.value.query.id).toBeUndefined();
    expect(byId("comp-detail").exists()).toBe(false);
  });

  it("shows the placeholder, without statistics, when no competition is selected", async () => {
    const server = fakeApi();
    const { byId } = await render(signedIn("coach"), server.api, store, "/competitions");
    await settle();
    expect(byId("no-selection").exists()).toBe(true);
    expect(byId("competitions-stats-tiles").exists()).toBe(false);
  });

  it("opens a sub-page under the page, the shared data loaded once", async () => {
    const server = fakeApi();
    const { byId, wrapper, router } = await render(signedIn("coach"), server.api, store, "/bureau/competitions/bilan");
    await settle();
    expect(byId("balance-pane").exists()).toBe(true);
    expect(wrapper.find("h1").text()).toBe("Bilan");
    expect(server.calls.map((c) => c.path)).not.toContain("/api/helloasso/items");
    await router.push("/bureau/competitions/helloasso");
    await settle();
    expect(byId("helloasso-pane").exists()).toBe(true);
    expect(server.calls.filter((c) => c.path === "/api/helloasso/items")).toHaveLength(1);
    expect(server.calls.filter((c) => c.path === "/api/competitions")).toHaveLength(1);
  });

  it("opens Bilan offline on a coach's device", async () => {
    await store.start(USER.uid);
    await store.save("competitions", USER.uid, COMPETITIONS, null, "/api/competitions");
    await store.save("competitors", USER.uid, CONTACTS, null, "/api/members/competitors");
    const { byId, router } = await render(offline, fakeApi({ down: true }).api, store, "/bureau/competitions/bilan");
    await settle();
    expect(byId("balance-pane").exists()).toBe(true);
    expect(byId("sub-side-helloasso").attributes("aria-disabled")).toBe("true");
    expect(router.currentRoute.value.fullPath).toBe("/bureau/competitions/bilan");
  });

  it("sends a device without the coaches' copy back to the list offline", async () => {
    await store.start(USER.uid);
    await store.save("competitions", USER.uid, COMPETITIONS, null, "/api/competitions");
    const { byId, router } = await render(offline, fakeApi({ down: true }).api, store, "/bureau/competitions/bilan");
    await settle();
    expect(router.currentRoute.value.fullPath).toBe("/bureau/competitions?reserve=bilan");
    expect(byId("balance-pane").exists()).toBe(false);
    expect(byId("comp-count").text()).toBe("1 compétition · 1 archivée");
  });
  it("opens a competition from Coachs on the list", async () => {
    const { all, byId, router } = await render(signedIn("coach"), fakeApi().api, store, "/bureau/competitions/coachs");
    await settle();
    await all("coach-competition")[0]!.trigger("click");
    await settle();
    expect(router.currentRoute.value.fullPath).toBe("/bureau/competitions?id=10");
    expect(byId("detail-name").text()).toBe("Coupe du Rhône");
  });
});
