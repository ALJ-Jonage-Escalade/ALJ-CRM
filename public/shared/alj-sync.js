/* Keeps a page's data up to date through the API (replaces the Firestore listeners).
   Classic script (not a module): usable from the PWA pages through <script> as well as
   from the bureau modules. Exposes window.ALJSync.

   - poll(url, opts): loads url now, then every intervalMs while the page is visible;
     reloads when the page becomes visible again, when the network comes back, and on
     demand (refresh() right after the user's own write). Sends If-None-Match so an
     unchanged poll is a 304 without body. Responses are never put in the HTTP cache.
     opts.etag: ETag of data the page already has (offline store, alj-store.js), so the
     first poll can be a 304 too; onData(data, etag) gets the new one. After stop(), an
     answer still on its way is dropped: neither onData nor onStatus is called.
   - request(fetchFn, method, url, body): JSON call for a write; rejects with an Error
     carrying the server's message, its HTTP `status` and machine `code` (e.g.
     "already_paid"). Without a `status`, the request never reached the server. */
(function () {
  "use strict";

  function poll(url, opts) {
    const o = Object.assign({ intervalMs: 20000, onData() {}, onStatus() {} }, opts || {});
    if (typeof o.fetch !== "function") throw new Error("ALJSync.poll: opts.fetch is required");
    let etag = o.etag || null;
    let timer = null;
    let inFlight = null;
    let again = false;
    let stopped = false;

    function schedule() {
      clearTimeout(timer);
      if (!stopped) timer = setTimeout(tick, o.intervalMs);
    }
    function tick() {
      if (document.hidden) { schedule(); return; }  // paused while hidden
      refresh();
    }

    async function load() {
      const headers = etag ? { "If-None-Match": etag } : {};
      let res;
      try {
        res = await o.fetch(url, { headers, cache: "no-store" });
      } catch (error) {
        if (!stopped) o.onStatus(navigator.onLine === false ? "offline" : "error", { error });
        return;
      }
      if (stopped) return;  // stopped while loading (logout, other season): answer dropped
      if (res.status === 304) { o.onStatus("ok", { changed: false }); return; }
      if (!res.ok) { o.onStatus("error", { status: res.status }); return; }
      let data;
      try { data = await res.json(); } catch (error) { if (!stopped) o.onStatus("error", { error }); return; }
      if (stopped) return;
      etag = res.headers.get("ETag");
      o.onData(data, etag);
      o.onStatus("ok", { changed: true });
    }

    /* Concurrent calls are merged: one more load runs after the current one. */
    function refresh() {
      if (stopped) return Promise.resolve();
      if (inFlight) { again = true; return inFlight; }
      clearTimeout(timer);
      inFlight = load().finally(() => {
        inFlight = null;
        if (again) { again = false; return refresh(); }
        schedule();
      });
      return inFlight;
    }

    const onVisible = () => { if (!document.hidden) refresh(); };
    const onOnline = () => refresh();
    const onOffline = () => o.onStatus("offline", {});
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);

    function stop() {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    }

    refresh();
    return { refresh, stop };
  }

  async function request(fetchFn, method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetchFn(url, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) {
      // 422: rejected by the server's validation, one message per invalid field
      const detail = data && Array.isArray(data.detail) ? data.detail.map(x => x.msg).join(" ; ") : "";
      const err = new Error((data && data.message) || detail || ("HTTP " + res.status));
      err.status = res.status;
      err.code = data && data.code;
      throw err;
    }
    return data;
  }

  window.ALJSync = Object.freeze({ poll, request });
})();
