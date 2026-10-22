/* Keeps data up to date through the API by polling (TypeScript port of poll() in web/shared/alj-sync.js, which the
   pages not migrated yet still use; plan decision D2: same behaviour, no rewrite).

   poll(url, opts) loads url now, then every intervalMs while the page is visible; reloads when the page becomes
   visible again, when the network comes back, and on demand (refresh()). Sends If-None-Match so an unchanged poll is
   a 304 without body. Responses are never put in the HTTP cache. opts.etag: ETag of data the caller already has
   (offline copy), so the first poll can be a 304 too; onData(data, etag) gets the new one. After stop(), an answer
   still on its way is dropped: neither onData nor onStatus is called. */
import type { ApiFetch } from "./api";

/** ok: answered (changed or not); offline: the browser says the network is down; error: refused or unreachable. */
export type PollStatus = "ok" | "offline" | "error";

/** changed: the data was new (false for a 304); status: HTTP status of a refusal; error: what fetch threw. */
export interface PollInfo {
  changed?: boolean;
  status?: number;
  error?: unknown;
}

export interface PollOptions<T> {
  fetch: ApiFetch;
  intervalMs?: number;
  etag?: string | null;
  onData: (data: T, etag: string | null) => void;
  onStatus?: (status: PollStatus, info: PollInfo) => void;
}

export interface Poll {
  /** Loads now; calls made while a load runs are merged into one more load after it. */
  refresh(): Promise<void>;
  stop(): void;
}

export const POLL_INTERVAL_MS = 20_000;

export function poll<T>(url: string, opts: PollOptions<T>): Poll {
  const intervalMs = opts.intervalMs ?? POLL_INTERVAL_MS;
  const onStatus = opts.onStatus ?? (() => {});
  let etag = opts.etag ?? null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inFlight: Promise<void> | null = null;
  let again = false;
  let stopped = false;

  function schedule(): void {
    clearTimeout(timer);
    if (!stopped) timer = setTimeout(tick, intervalMs);
  }

  function tick(): void {
    if (document.hidden) {
      schedule();  // paused while hidden
      return;
    }
    void refresh();
  }

  async function load(): Promise<void> {
    const headers: Record<string, string> = etag ? { "If-None-Match": etag } : {};
    let res: Response;
    try {
      res = await opts.fetch(url, { headers, cache: "no-store" });
    } catch (error) {
      if (!stopped) onStatus(navigator.onLine === false ? "offline" : "error", { error });
      return;
    }
    if (stopped) return;  // stopped while loading (logout, other season): answer dropped
    if (res.status === 304) {
      onStatus("ok", { changed: false });
      return;
    }
    if (!res.ok) {
      onStatus("error", { status: res.status });
      return;
    }
    let data: T;
    try {
      data = (await res.json()) as T;
    } catch (error) {
      if (!stopped) onStatus("error", { error });
      return;
    }
    if (stopped) return;
    etag = res.headers.get("ETag");
    opts.onData(data, etag);
    onStatus("ok", { changed: true });
  }

  function refresh(): Promise<void> {
    if (stopped) return Promise.resolve();
    if (inFlight) {
      again = true;
      return inFlight;
    }
    clearTimeout(timer);
    inFlight = load().finally(() => {
      inFlight = null;
      if (again) {
        again = false;
        return refresh();
      }
      schedule();
    });
    return inFlight;
  }

  const onVisible = () => {
    if (!document.hidden) void refresh();
  };
  const onOnline = () => void refresh();
  const onOffline = () => onStatus("offline", {});
  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);

  function stop(): void {
    stopped = true;
    clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onOnline);
    window.removeEventListener("offline", onOffline);
  }

  void refresh();
  return { refresh, stop };
}
