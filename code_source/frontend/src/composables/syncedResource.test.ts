import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref, type Ref } from "vue";
import type { ApiFetch } from "../lib/api";
import type { OfflineStore, Stored } from "../lib/store";
import { useSyncedResource } from "./syncedResource";

/** A server answering each url with its current body and a matching ETag (304 when the client already has it). */
function fakeServer() {
  const bodies = new Map<string, unknown>();
  const statuses = new Map<string, number>();
  const calls: { url: string; ifNoneMatch: string | null; cache?: RequestCache }[] = [];
  const pending: ((r: Response) => void)[] = [];
  let hold = false;
  const etagOf = (url: string) => `"${JSON.stringify(bodies.get(url)).length}-${url}-${JSON.stringify(bodies.get(url))}"`;
  const fetch: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const ifNoneMatch = new Headers(init?.headers).get("If-None-Match");
    calls.push({ url, ifNoneMatch, cache: init?.cache });
    const answer = (): Response => {
      const status = statuses.get(url);
      if (status) return new Response(JSON.stringify({ status: "error", message: "refusé" }), { status });
      const etag = etagOf(url);
      if (ifNoneMatch === etag) return new Response(null, { status: 304, headers: { ETag: etag } });
      return new Response(JSON.stringify(bodies.get(url)), { status: 200, headers: { ETag: etag, "Content-Type": "application/json" } });
    };
    if (!hold) return answer();
    return new Promise<Response>((resolve) => pending.push(() => resolve(answer())));
  });
  return {
    fetch,
    calls,
    set: (url: string, body: unknown) => bodies.set(url, body),
    refuse: (url: string, status: number) => statuses.set(url, status),
    holdAnswers: () => (hold = true),
    releaseAnswers: () => {
      hold = false;
      pending.splice(0).forEach((resolve) => resolve(new Response()));
    },
  };
}

function setHidden(hidden: boolean): void {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event("visibilitychange"));
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  setHidden(false);
});

function start(server: ReturnType<typeof fakeServer>, url: Ref<string | null> | string = "/api/members") {
  const scope = effectScope();
  const resource = scope.run(() => useSyncedResource<{ n: number }>("members", url, { offline: false, intervalMs: 1000, fetch: server.fetch }))!;
  return { scope, resource };
}

describe("useSyncedResource (online)", () => {
  it("loads, then polls with the ETag: an unchanged poll is a 304 and keeps the data", async () => {
    const server = fakeServer();
    server.set("/api/members", { n: 1 });
    const { resource } = start(server);
    expect(resource.state.value).toBe("loading");
    await flushPromises();
    expect(resource.data.value).toEqual({ n: 1 });
    expect(resource.state.value).toBe("ok");
    expect(server.calls[0]).toEqual({ url: "/api/members", ifNoneMatch: null, cache: "no-store" });

    const first = resource.data.value;
    await vi.advanceTimersByTimeAsync(1000);
    expect(server.calls).toHaveLength(2);
    expect(server.calls[1]!.ifNoneMatch).not.toBeNull();
    expect(resource.data.value).toBe(first);  // 304: same object, nothing re-rendered

    server.set("/api/members", { n: 2 });
    await vi.advanceTimersByTimeAsync(1000);
    expect(resource.data.value).toEqual({ n: 2 });
  });

  it("pauses while the page is hidden and reloads when it is visible again", async () => {
    const server = fakeServer();
    server.set("/api/members", { n: 1 });
    start(server);
    await flushPromises();
    setHidden(true);
    await vi.advanceTimersByTimeAsync(5000);
    expect(server.calls).toHaveLength(1);
    setHidden(false);
    await flushPromises();
    expect(server.calls).toHaveLength(2);
  });

  it("reloads on refresh() and when the network comes back", async () => {
    const server = fakeServer();
    server.set("/api/members", { n: 1 });
    const { resource } = start(server);
    await flushPromises();
    server.set("/api/members", { n: 5 });
    await resource.refresh();
    expect(resource.data.value).toEqual({ n: 5 });
    window.dispatchEvent(new Event("online"));
    await flushPromises();
    expect(server.calls).toHaveLength(3);
    window.dispatchEvent(new Event("offline"));
    expect(resource.state.value).toBe("offline");
  });

  it("stops with its scope: no more polls, and an answer on its way is dropped", async () => {
    const server = fakeServer();
    server.set("/api/members", { n: 1 });
    const { scope, resource } = start(server);
    await flushPromises();
    server.set("/api/members", { n: 2 });
    server.holdAnswers();
    await vi.advanceTimersByTimeAsync(1000);
    scope.stop();
    server.releaseAnswers();
    await flushPromises();
    expect(resource.data.value).toEqual({ n: 1 });
    await vi.advanceTimersByTimeAsync(10_000);
    window.dispatchEvent(new Event("online"));
    expect(server.calls).toHaveLength(2);
  });

  it("switches url: data is reset and a late answer of the former url is dropped", async () => {
    const server = fakeServer();
    server.set("/api/members", { n: 1 });
    server.set("/api/members?season=2025-2026", { n: 25 });
    const url = ref<string | null>("/api/members");
    server.holdAnswers();
    const { resource } = start(server, url);
    url.value = "/api/members?season=2025-2026";
    await nextTick();
    expect(resource.data.value).toBeNull();
    server.releaseAnswers();
    await flushPromises();
    expect(resource.data.value).toEqual({ n: 25 });
    await vi.advanceTimersByTimeAsync(1000);
    expect(server.calls.map((c) => c.url)).toEqual(["/api/members", "/api/members?season=2025-2026", "/api/members?season=2025-2026"]);

    url.value = null;
    await nextTick();
    await vi.advanceTimersByTimeAsync(5000);
    expect(server.calls).toHaveLength(3);
  });

  it("reports refusals with their status and stops when signed out (401)", async () => {
    const server = fakeServer();
    server.refuse("/api/members", 404);
    const { resource } = start(server);
    await flushPromises();
    expect([resource.state.value, resource.httpStatus.value, resource.data.value]).toEqual(["error", 404, null]);
    await vi.advanceTimersByTimeAsync(1000);
    expect(server.calls).toHaveLength(2);  // still polling: a temporary error is retried

    server.refuse("/api/members", 401);
    await vi.advanceTimersByTimeAsync(1000);
    expect(resource.httpStatus.value).toBe(401);
    await vi.advanceTimersByTimeAsync(5000);
    expect(server.calls).toHaveLength(3);
  });
});

/** The offline store in memory (lib/store.ts is tested on its own): one copy per name, owned by a user. */
function memoryStore() {
  const copies = new Map<string, Stored & { uid: string }>();
  const store: OfflineStore = {
    start: vi.fn(async () => {}),
    // vi.fn() drops the type parameter of load<T>
    load: vi.fn(async (name: string, uid: string | null) => {
      const copy = copies.get(name);
      return copy && copy.uid === uid ? { data: copy.data, etag: copy.etag, savedAt: copy.savedAt, url: copy.url } : null;
    }) as OfflineStore["load"],
    save: vi.fn(async (name: string, uid: string | null, data: unknown, etag: string | null, url: string | null = null) => {
      if (uid) copies.set(name, { uid, data, etag, savedAt: Date.now(), url });
    }),
    touch: vi.fn(async () => {}),
    queue: vi.fn(async () => {}),
    queued: vi.fn(async () => []),
    unqueue: vi.fn(async () => {}),
    clearAll: vi.fn(async () => copies.clear()),
  };
  return { store, copies };
}

function startOffline(
  server: ReturnType<typeof fakeServer>,
  store: OfflineStore,
  uid: Ref<string | null> | string | null = "u1",
  select?: (answer: unknown) => { n: number },
) {
  const scope = effectScope();
  const resource = scope.run(() =>
    useSyncedResource<{ n: number }>("directory", "/api/members", { offline: true, uid, select, intervalMs: 1000, fetch: server.fetch, store }),
  )!;
  return { scope, resource };
}

describe("useSyncedResource (offline)", () => {
  const SAVED_AT = Date.UTC(2026, 9, 1, 8);

  it("shows the copy at once, sends its ETag, and a 304 confirms it without writing it again", async () => {
    const server = fakeServer();
    server.set("/api/members", { n: 1 });
    const { store, copies } = memoryStore();
    const etag = `"${JSON.stringify({ n: 1 }).length}-/api/members-${JSON.stringify({ n: 1 })}"`;
    copies.set("directory", { uid: "u1", data: { n: 1 }, etag, savedAt: SAVED_AT, url: "/api/members" });
    server.holdAnswers();
    const { resource } = startOffline(server, store);
    await flushPromises();
    expect(resource.data.value).toEqual({ n: 1 });
    expect(resource.dataAt.value).toEqual(new Date(SAVED_AT));
    expect(resource.state.value).toBe("loading");
    expect(server.calls[0]!.ifNoneMatch).toBe(etag);
    server.releaseAnswers();
    await flushPromises();
    expect(resource.state.value).toBe("ok");
    expect(store.touch).toHaveBeenCalledWith("directory", "u1");
    expect(store.save).not.toHaveBeenCalled();
    expect(resource.dataAt.value!.getTime()).toBeGreaterThan(SAVED_AT);
  });

  it("keeps every new answer, as the screen selected it, with its url", async () => {
    const server = fakeServer();
    server.set("/api/members", { n: 2, secret: "x" });
    const { store, copies } = memoryStore();
    const { resource } = startOffline(server, store, "u1", (answer) => ({ n: (answer as { n: number }).n }));
    await flushPromises();
    expect(resource.data.value).toEqual({ n: 2 });
    expect(copies.get("directory")).toMatchObject({ uid: "u1", data: { n: 2 }, url: "/api/members" });
    expect(copies.get("directory")!.etag).toBeTruthy();
  });

  it("shows the copy the former page wrote (no url)", async () => {
    const server = fakeServer();
    const { store, copies } = memoryStore();
    copies.set("directory", { uid: "u1", data: { n: 7 }, etag: null, savedAt: SAVED_AT, url: null });
    server.holdAnswers();
    const { resource } = startOffline(server, store);
    await flushPromises();
    expect(resource.data.value).toEqual({ n: 7 });
  });

  it("does not show the copy of another url, nor another user's", async () => {
    const server = fakeServer();
    server.set("/api/members", { n: 3 });
    const { store, copies } = memoryStore();
    copies.set("directory", { uid: "u1", data: { n: 25 }, etag: null, savedAt: SAVED_AT, url: "/api/members?season=2025-2026" });
    server.holdAnswers();
    const { resource } = startOffline(server, store);
    await flushPromises();
    expect(resource.data.value).toBeNull();
    expect(server.calls[0]!.ifNoneMatch).toBeNull();

    const other = startOffline(server, store, "u2");
    copies.set("directory", { uid: "u1", data: { n: 1 }, etag: null, savedAt: SAVED_AT, url: "/api/members" });
    await flushPromises();
    expect(other.resource.data.value).toBeNull();
  });

  it("keeps showing the copy and its date while the network is down", async () => {
    const server = fakeServer();
    const { store, copies } = memoryStore();
    copies.set("directory", { uid: "u1", data: { n: 1 }, etag: null, savedAt: SAVED_AT, url: "/api/members" });
    vi.mocked(server.fetch).mockRejectedValue(new TypeError("Failed to fetch"));
    Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false });
    try {
      const { resource } = startOffline(server, store);
      await flushPromises();
      expect([resource.state.value, resource.data.value, resource.dataAt.value]).toEqual(["offline", { n: 1 }, new Date(SAVED_AT)]);
    } finally {
      Object.defineProperty(navigator, "onLine", { configurable: true, get: () => true });
    }
  });

  it.each([401, 403])("wipes the store and stops on a %i (role lost)", async (status) => {
    const server = fakeServer();
    server.refuse("/api/members", status);
    const { store, copies } = memoryStore();
    copies.set("directory", { uid: "u1", data: { n: 1 }, etag: null, savedAt: SAVED_AT, url: "/api/members" });
    const { resource } = startOffline(server, store);
    await flushPromises();
    expect(store.clearAll).toHaveBeenCalled();
    expect([resource.data.value, resource.dataAt.value, resource.httpStatus.value]).toEqual([null, null, status]);
    await vi.advanceTimersByTimeAsync(5000);
    expect(server.calls).toHaveLength(1);
  });

  it("keeps nothing without a user, and starts again with the copy of the next user", async () => {
    const server = fakeServer();
    server.set("/api/members", { n: 4 });
    const { store, copies } = memoryStore();
    copies.set("directory", { uid: "u2", data: { n: 2 }, etag: null, savedAt: SAVED_AT, url: "/api/members" });
    const uid = ref<string | null>(null);
    server.holdAnswers();
    const { resource } = startOffline(server, store, uid);
    await flushPromises();
    expect(store.load).not.toHaveBeenCalled();
    server.releaseAnswers();
    await flushPromises();
    expect(resource.data.value).toEqual({ n: 4 });
    expect(store.save).not.toHaveBeenCalled();

    server.holdAnswers();
    uid.value = "u2";
    await flushPromises();
    expect(store.start).toHaveBeenCalledWith("u2");
    expect(resource.data.value).toEqual({ n: 2 });
  });
});
