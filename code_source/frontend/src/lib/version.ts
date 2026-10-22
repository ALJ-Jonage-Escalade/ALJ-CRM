/** App version, update check and service worker (web/sw.js, network first, until the cutover phase). */
export const APP_VERSION: string = __APP_VERSION__;

/** Version currently deployed (null offline or on error). */
export async function deployedVersion(fetchImpl: typeof fetch = (...args) => fetch(...args)): Promise<string | null> {
  try {
    const res = await fetchImpl("/api/web-version", { cache: "no-store" });
    if (!res.ok) return null;
    const body: unknown = await res.json();
    const version = (body as { app_version?: unknown }).app_version;
    return typeof version === "string" && version ? version : null;
  } catch {
    return null;  // offline
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

export function registerServiceWorker(): void {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch((err: unknown) => console.warn("Service Worker :", err));
  }
}
