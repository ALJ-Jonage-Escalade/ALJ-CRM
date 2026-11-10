/** App version, update check and service worker (src/sw.ts, built into dist/sw.js, served at /sw.js). */
export const APP_VERSION: string = __APP_VERSION__;

/** Version currently deployed (null offline or on error). */
export async function deployedVersion(fetchImpl: typeof fetch = (...args) => fetch(...args)): Promise<string | null> {
  try {
    const res = await fetchImpl("/api/web-version", { cache: "no-store" });
    if (!res.ok) {
      return null;
    }
    const body: unknown = await res.json();
    const version = (body as { app_version?: unknown }).app_version;
    return typeof version === "string" && version ? version : null;
  } catch {
    return null; // offline
  }
}

/** Drops the service workers and caches, then reloads: the page gets the deployed version. */
export async function forceUpdate(): Promise<void> {
  try {
    if ("serviceWorker" in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((r) => r.unregister()));
    }
    if ("caches" in window) {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch (e) {
    console.warn("Mise à jour forcée :", e);
  }
  location.reload();
}

const CHUNK_RELOAD_STORAGE = "alj_chunk_reload";

/** Registers the built service worker (not in `npm run dev`: there is no build to precache). After a deploy, a page
 * opened before it may ask for a chunk of its own build that is gone: it reloads instead of breaking. */
export function registerServiceWorker(): void {
  if (!import.meta.env.PROD) {
    return;
  }
  window.addEventListener("vite:preloadError", () => {
    // Once a minute at most: a chunk missing after the reload too is a server fault, not a loop to start
    const last = Number(sessionStorage.getItem(CHUNK_RELOAD_STORAGE) ?? 0);
    if (Date.now() - last < 60_000) {
      return;
    }
    sessionStorage.setItem(CHUNK_RELOAD_STORAGE, String(Date.now()));
    location.reload();
  });
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch((err: unknown) => console.warn("Service Worker :", err));
  }
}
