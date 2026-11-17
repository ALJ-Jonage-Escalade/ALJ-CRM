/// <reference lib="webworker" />
/* Service worker of the app (decision D9), built by vite-plugin-pwa (injectManifest) into dist/sw.js and served by
   FastAPI at /sw.js: same address and scope (/) as the former hand-written web/sw.js, so the browsers that have it
   install this one on their next visit, without a manual refresh.
   - Build files (hashed names, plus the entry page): precached at install, served from the cache; the entries of
     earlier builds are deleted. No hand-kept list, no cache name to bump.
   - Pages of the app: network first (a deploy is seen at once), the precached entry page offline.
   - Everything else (API, /runtime-config.js, manifest, Google): network only, never cached. */
import { clientsClaim } from "workbox-core";
import { cleanupOutdatedCaches, matchPrecache, precacheAndRoute } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";
import type { RouteHandlerCallbackOptions } from "workbox-core/types";

declare const self: ServiceWorkerGlobalScope;

/** Entry page of the app, as precached (Vite base /spa/, api/web/pages.py). */
const ENTRY_PAGE = "/spa/index.html";
/** Prefix of the caches of the former web/sw.js ("alj-escalade-v26"…). Remove with their cleanup after 2026-11-24, with the
    store's legacy snapshots (lib/store.ts LEGACY_PREFIX): by then every device that ran the former pages has opened the app. */
const LEGACY_CACHE_PREFIX = "alj-escalade-v";
/** Page addresses answered by the app's entry page (api/web/pages.py, src/router.ts). */
const APP_PAGES = [/^\/$/, /^\/competitions(\/|$)/, /^\/index$/, /^\/bureau(\/|$)/];

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

async function networkThenEntryPage({ request }: RouteHandlerCallbackOptions): Promise<Response> {
  try {
    return await fetch(request);
  } catch {
    return (await matchPrecache(ENTRY_PAGE)) ?? Response.error();
  }
}
registerRoute(new NavigationRoute(networkThenEntryPage, { allowlist: APP_PAGES }));

// The new version takes over at once (no tab left on the former worker); its pages reload on a missing chunk (main.ts)
void self.skipWaiting();
clientsClaim();

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith(LEGACY_CACHE_PREFIX)).map((k) => caches.delete(k)))),
  );
});
