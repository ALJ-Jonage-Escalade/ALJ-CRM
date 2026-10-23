"""PWA service worker (frontend/src/sw.ts, built into dist/sw.js, served at /sw.js): hashed precache, never-cached
routes, pages served offline, and the update of the browsers that still have the former hand-written worker.

Service workers are blocked in the other tests (a worker would keep state between them)."""
import re

import pytest
from playwright.sync_api import expect

from helpers.data import eventually

pytestmark = pytest.mark.browser_context_args(service_workers="allow")

_CACHE_KEYS = "() => caches.keys()"
_ALL_CACHED_URLS = """async () => {
  const urls = [];
  for (const name of await caches.keys()) {
    for (const r of await (await caches.open(name)).keys()) urls.push(new URL(r.url).pathname);
  }
  return urls;
}"""
_WORKER_URL = "() => navigator.serviceWorker.controller && navigator.serviceWorker.controller.scriptURL"

# The former web/sw.js as browsers still have it: a cache named after the web version, network first
_LEGACY_WORKER = """
const CACHE_NAME = "alj-escalade-v26";
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then((c) => c.addAll(["/competitions", "/manifest.webmanifest"])));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== self.location.origin) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
"""


def _controlled(page, path="/bureau/"):
    """Loads the page until the service worker is installed and controls it."""
    page.goto(path)
    page.evaluate("() => navigator.serviceWorker.ready")
    if not page.evaluate("() => !!navigator.serviceWorker.controller"):
        page.reload()
    assert page.evaluate("() => !!navigator.serviceWorker.controller")
    return page


def test_precache_is_the_build(page):
    """Precache = the build's files (hashed names, entry page); the API and the runtime config are never cached."""
    _controlled(page)
    cached = page.evaluate(_ALL_CACHED_URLS)
    assert "/spa/index.html" in cached
    assert any(u.startswith("/spa/assets/index-") and u.endswith(".js") for u in cached), cached
    assert any(u.startswith("/spa/assets/PlanningPage-") for u in cached), "pages loaded on demand are precached too"
    assert not any(k.startswith("alj-escalade-v") for k in page.evaluate(_CACHE_KEYS))

    page.evaluate("() => Promise.all([fetch('/api/web-version'), fetch('/runtime-config.js'), fetch('/health')])")
    cached = page.evaluate(_ALL_CACHED_URLS)
    for path in ("/api/web-version", "/runtime-config.js", "/health", "/bureau/"):
        assert path not in cached, f"{path} cached"


def test_pages_open_offline(page, context):
    _controlled(page)
    expect(page.locator("#gate-login")).to_be_visible()
    context.set_offline(True)
    try:
        page.reload()
        # Shell rendered from the precache: menu and login gate, no browser error page
        expect(page.locator("nav a[data-page='adherents']")).to_be_visible()
        expect(page.locator("#gate")).to_be_visible()
        for path in ("/bureau/competitions", "/competitions", "/index", "/bureau/planning"):
            page.goto(path)
            expect(page.locator("#gate")).to_be_visible()
        page.goto("/")  # the server's redirect, done by the app offline
        expect(page).to_have_url(re.compile(r"/competitions$"))
    finally:
        context.set_offline(False)


def test_former_worker_is_replaced(page, context):
    """A browser with the former worker (and its cache) gets the built one on its next visit, without a manual
    refresh: the former cache is deleted and the page keeps working."""
    context.route("**/sw.js", lambda route: route.fulfill(body=_LEGACY_WORKER, content_type="application/javascript",
                                                          headers={"Cache-Control": "no-cache"}))
    _controlled(page, "/competitions")
    assert "alj-escalade-v26" in page.evaluate(_CACHE_KEYS)
    legacy_url = page.evaluate(_WORKER_URL)

    context.unroute("**/sw.js")
    page.goto("/competitions")  # next visit: the browser checks /sw.js, gets the built worker

    def replaced():
        page.evaluate("() => navigator.serviceWorker.getRegistration().then(r => r && r.update())")
        keys = page.evaluate(_CACHE_KEYS)
        assert "alj-escalade-v26" not in keys, keys
        assert any(k.startswith("workbox-precache") for k in keys), keys
    eventually(replaced, timeout=20)
    assert page.evaluate(_WORKER_URL) == legacy_url  # same address: one registration, updated in place
    expect(page.locator("#gate-login")).to_be_visible()
