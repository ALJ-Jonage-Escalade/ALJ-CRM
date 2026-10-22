import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref, type Ref } from "vue";
import type { ApiFetch } from "../lib/api";
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
