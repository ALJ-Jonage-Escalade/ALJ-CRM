/* Outils › Clés (plans/club-keys.md), through the app's routes: the page talks to a fake API. */
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { AUTH_KEY, type Auth } from "../../composables/auth";
import { dialogs } from "../../composables/dialogs";
import { API_KEY, type ApiFetch } from "../../lib/api";
import { CLIENT_KEY, createApiClient } from "../../lib/client";
import type { Role } from "../../lib/roles";
import { routes } from "../../router";
import type { Key } from "./keys";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Answer = (body: unknown) => Response;

async function render(role: Role, keys: Key[], extra: Record<string, Answer> = {}) {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const answers: Record<string, Answer> = {
    "GET /api/seasons": () => json({ seasons: ["2026-2027"], active: "2026-2027" }),
    "GET /api/keys": () => json(keys),
    ...extra,
  };
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url, "http://alj.test");
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path: u.pathname, body });
    const answer = answers[`${method} ${u.pathname}`];
    return answer ? answer(body) : json({}, 404);
  });
  const auth: Auth = {
    state: ref({ status: "signedIn", user: { uid: "u1", email: "u@alj.example" }, role }),
    login: vi.fn(),
    logout: vi.fn(async () => {}),
    retry: vi.fn(async () => {}),
    stop: vi.fn(),
  };
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push("/bureau/outils/cles");
  mount(RouterView, {
    attachTo: document.body,
    global: {
      plugins: [router],
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") },
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  await flushPromises();
  const byId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const all = (id: string) => [...document.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`)];
  const sent = (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path);
  return { byId, all, sent };
}

const HARRY = {
  user_id: 7,
  last_name: "POTTER",
  first_name: "Harry",
  given_on: "2026-09-12",
  comment: "Remise au forum",
  member_this_season: true,
  season: "2026-2027",
};
const KEYS: Key[] = [
  { id: 1, code: "10", status: "assigned", holder: HARRY },
  { id: 2, code: "2", status: "available", holder: null },
  { id: 3, code: "B1", status: "available", holder: null },
];
const MEMBERS = {
  season: "2026-2027",
  creneaux: [],
  members: [
    { user_id: 7, last_name: "POTTER", first_name: "Harry" },
    { user_id: 8, last_name: "WEASLEY", first_name: "Ron" },
    { user_id: 8, last_name: "WEASLEY", first_name: "Ron" }, // two memberships, one person
    { user_id: 9, last_name: "GRANGER", first_name: "Hermione" },
  ],
};
const typeIn = async (el: HTMLElement | null, value: string) => {
  (el as HTMLInputElement).value = value;
  el!.dispatchEvent(new Event("input"));
  await flushPromises();
};

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("OutilsKeysPage", () => {
  it("lists the keys in natural order with their counts, read only for a coach", async () => {
    const { byId, all } = await render("coach", KEYS);
    expect(all("key-code").map((c) => c.textContent.trim())).toEqual(["2", "10", "B1"]);
    expect(byId("key-counts")!.textContent.trim()).toBe("1 attribuée · 2 disponibles · 0 archivée");
    expect(byId("key-add")).toBeNull();
  });

  it("filters the keys on the search", async () => {
    const { byId, all } = await render("coach", KEYS);
    const search = byId("key-search") as HTMLInputElement;
    search.value = "b";
    search.dispatchEvent(new Event("input"));
    await flushPromises();
    expect(all("key-code").map((c) => c.textContent.trim())).toEqual(["B1"]);
  });

  it("lets an admin add a key, then reloads the list", async () => {
    const keys = [...KEYS];
    const { byId, all, sent } = await render("admin", keys, {
      "POST /api/keys": (body) => {
        const added: Key = { id: 4, code: (body as { code: string }).code, status: "available", holder: null };
        keys.push(added);
        return json(added, 201);
      },
    });
    vi.spyOn(dialogs, "prompt").mockResolvedValue("7");
    byId("key-add")!.click();
    await flushPromises();
    expect(sent("POST", "/api/keys").map((c) => c.body)).toEqual([{ code: "7" }]);
    expect(all("key-code").map((c) => c.textContent.trim())).toEqual(["2", "7", "10", "B1"]);
    expect(byId("toast")!.textContent).toBe("✅ Clé « 7 » ajoutée.");
  });

  it("shows why a key could not be added", async () => {
    const { byId } = await render("admin", KEYS, {
      "POST /api/keys": () => json({ status: "error", message: "La clé « 2 » existe déjà.", code: "duplicate_code" }, 409),
    });
    vi.spyOn(dialogs, "prompt").mockResolvedValue("2");
    byId("key-add")!.click();
    await flushPromises();
    expect(byId("toast")!.textContent).toBe("❌ La clé « 2 » existe déjà.");
  });

  it("shows who holds a key, links to their record and flags those who did not renew", async () => {
    const gone = { ...HARRY, user_id: 9, last_name: "DIGGORY", first_name: "Cedric", member_this_season: false, season: "2025-2026" };
    const keys: Key[] = [...KEYS, { id: 4, code: "11", status: "assigned", holder: gone }];
    const { byId, all } = await render("coach", keys);
    const holders = all("key-holder");
    expect(holders.map((h) => h.textContent.trim())).toEqual(["POTTER Harry", "DIGGORY Cedric ⚠️"]);
    expect(holders[0]!.querySelector("a")!.getAttribute("href")).toBe("/bureau/adherents?id=7&saison=2026-2027");
    expect(holders[1]!.querySelector("a")!.getAttribute("href")).toBe("/bureau/adherents?id=9&saison=2025-2026");
    expect(all("key-given-on").map((d) => d.textContent.trim())).toEqual(["12/09/2026", "12/09/2026"]);
    expect(byId("key-actions")).toBeNull(); // nothing to do for a coach

    (byId("key-only-flagged") as HTMLInputElement).click();
    await flushPromises();
    expect(all("key-code").map((c) => c.textContent.trim())).toEqual(["11"]);
  });

  it("lets an admin hand a key to a member of the season who holds none", async () => {
    const { byId, all, sent } = await render("admin", KEYS, {
      "GET /api/members": () => json(MEMBERS),
      "POST /api/keys/2/assignments": () => json({ status: "success" }),
    });
    byId("key-assign-2")!.click();
    await flushPromises();
    expect(all("assign-member").map((m) => m.textContent.trim())).toEqual([
      "GRANGER Hermione",
      "POTTER Harry — détient déjà la clé 10",
      "WEASLEY Ron",
    ]);
    expect(all("assign-member")[1]!.hasAttribute("disabled")).toBe(true);
    await typeIn(byId("assign-search"), "wea");
    expect(all("assign-member").map((m) => m.textContent.trim())).toEqual(["WEASLEY Ron"]);
    all("assign-member")[0]!.click();
    await flushPromises();
    await typeIn(byId("assign-date"), "2026-10-01");
    await typeIn(byId("assign-comment"), "Caution");
    byId("assign-submit")!.click();
    await flushPromises();
    expect(sent("POST", "/api/keys/2/assignments").map((c) => c.body)).toEqual([
      { user_id: 8, given_on: "2026-10-01", comment: "Caution" },
    ]);
    expect(byId("toast")!.textContent).toBe("✅ Clé « 2 » remise à WEASLEY Ron.");
    expect(sent("GET", "/api/keys")).toHaveLength(2);
  });

  it("lets an admin record the return of a key", async () => {
    const { byId, sent } = await render("admin", KEYS, { "POST /api/keys/1/return": () => json({ status: "success" }) });
    byId("key-return-1")!.click();
    await flushPromises();
    expect((byId("return-date") as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}$/); // today
    await typeIn(byId("return-date"), "2027-06-30");
    await typeIn(byId("return-comment"), "Fin de saison");
    byId("return-submit")!.click();
    await flushPromises();
    expect(sent("POST", "/api/keys/1/return").map((c) => c.body)).toEqual([{ returned_on: "2027-06-30", comment: "Fin de saison" }]);
    expect(byId("toast")!.textContent).toBe("✅ Retour de la clé « 10 » enregistré.");
  });
});
