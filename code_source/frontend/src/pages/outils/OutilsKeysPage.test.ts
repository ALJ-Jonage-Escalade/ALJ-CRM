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

const KEYS: Key[] = [
  { id: 1, code: "10", status: "assigned" },
  { id: 2, code: "2", status: "available" },
  { id: 3, code: "B1", status: "available" },
];

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
        const added: Key = { id: 4, code: (body as { code: string }).code, status: "available" };
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
});
