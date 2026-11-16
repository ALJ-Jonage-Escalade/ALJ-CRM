import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import type { ApiFetch } from "./api";
import { poll, POLL_INTERVAL_MS, type Poll } from "./sync";

const THINGS_URL = "/api/things";

function answer(status: number, body?: unknown, etag?: string): Response {
  const headers = etag ? { ETag: etag } : undefined;
  return status === 304 ? new Response(null, { status }) : new Response(JSON.stringify(body ?? {}), { status, headers });
}

function setHidden(hidden: boolean): void {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
}

describe("poll", () => {
  let running: Poll | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    setHidden(false);
  });

  afterEach(() => {
    running?.stop();
    running = undefined;
    vi.useRealTimers();
    vi.restoreAllMocks();
    setHidden(false);
  });

  function start(fetch: Mock<ApiFetch>, etag?: string | null) {
    const onData = vi.fn();
    const onStatus = vi.fn();
    running = poll(THINGS_URL, { fetch, etag, onData, onStatus, intervalMs: 1000 });
    return { onData, onStatus };
  }

  it("loads at once without the HTTP cache, then gives the data and its ETag", async () => {
    const fetch = vi.fn<ApiFetch>().mockResolvedValue(answer(200, { n: 1 }, '"v1"'));
    const { onData, onStatus } = start(fetch);
    await vi.waitFor(() => expect(onData).toHaveBeenCalledWith({ n: 1 }, '"v1"'));
    expect(fetch).toHaveBeenCalledWith(THINGS_URL, { headers: {}, cache: "no-store" });
    expect(onStatus).toHaveBeenCalledWith("ok", { changed: true });
  });

  it("sends the ETag it has, offline copy included, and keeps the data on a 304", async () => {
    const fetch = vi.fn<ApiFetch>().mockResolvedValue(answer(304));
    const { onData, onStatus } = start(fetch, '"v0"');
    await vi.waitFor(() => expect(onStatus).toHaveBeenCalledWith("ok", { changed: false }));
    expect(fetch).toHaveBeenCalledWith(THINGS_URL, { headers: { "If-None-Match": '"v0"' }, cache: "no-store" });
    expect(onData).not.toHaveBeenCalled();
  });

  it("polls again after the interval with the new ETag", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(answer(200, { n: 1 }, '"v1"'))
      .mockResolvedValue(answer(304));
    const { onData } = start(fetch);
    await vi.waitFor(() => expect(onData).toHaveBeenCalledOnce());
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch).toHaveBeenLastCalledWith(THINGS_URL, { headers: { "If-None-Match": '"v1"' }, cache: "no-store" });
  });

  it("waits while the page is hidden and reloads when it is shown again", async () => {
    const fetch = vi.fn<ApiFetch>().mockResolvedValue(answer(304));
    start(fetch);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    setHidden(true);
    await vi.advanceTimersByTimeAsync(3000);
    expect(fetch).toHaveBeenCalledOnce();
    setHidden(false);
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  });

  it("says offline when the browser is offline, error for a refusal or an unreadable body", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const failure = new TypeError("Failed to fetch");
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce(answer(500))
      .mockResolvedValueOnce(new Response("not json", { status: 200 }));
    const { onStatus, onData } = start(fetch);
    await vi.waitFor(() => expect(onStatus).toHaveBeenCalledWith("offline", { error: failure }));
    await running!.refresh();
    expect(onStatus).toHaveBeenLastCalledWith("error", { status: 500 });
    await running!.refresh();
    expect(onStatus).toHaveBeenLastCalledWith("error", { error: expect.any(SyntaxError) });
    expect(onData).not.toHaveBeenCalled();
  });

  it("says error, not offline, when the network is up but the call fails", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    const fetch = vi.fn<ApiFetch>().mockRejectedValue(new TypeError("Failed to fetch"));
    const { onStatus } = start(fetch);
    await vi.waitFor(() => expect(onStatus).toHaveBeenCalledWith("error", expect.anything()));
  });

  it("reloads when the network comes back and reports when it goes", async () => {
    const fetch = vi.fn<ApiFetch>().mockResolvedValue(answer(304));
    const { onStatus } = start(fetch);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    window.dispatchEvent(new Event("offline"));
    expect(onStatus).toHaveBeenCalledWith("offline", {});
    window.dispatchEvent(new Event("online"));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  });

  it("merges the refreshes asked during a load into one more load", async () => {
    let release: (response: Response) => void = () => {};
    const fetch = vi
      .fn()
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (release = resolve)))
      .mockResolvedValue(answer(304));
    start(fetch);
    const first = running!.refresh();
    void running!.refresh();
    release(answer(304));
    await first;
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    await Promise.resolve();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("drops an answer arriving after stop() and polls no more", async () => {
    let release: (response: Response) => void = () => {};
    const fetch = vi.fn<ApiFetch>(() => new Promise<Response>((resolve) => (release = resolve)));
    const { onData, onStatus } = start(fetch);
    running!.stop();
    release(answer(200, { n: 1 }, '"v1"'));
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(onData).not.toHaveBeenCalled();
    expect(onStatus).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledOnce();
    await running!.refresh();
    window.dispatchEvent(new Event("online"));
    expect(fetch).toHaveBeenCalledOnce();
  });
});
