/* Offline store of the phone pages (plan phase 5): the last data received from the API,
   kept in IndexedDB for read-only viewing without network. Classic script (not a module),
   exposes window.ALJStore. The only place that opens IndexedDB.

   - start(uid): call once signed in. Wipes the store when another user owned it, moves the
     old localStorage snapshots (alj_snapshot:*) in, and asks the browser not to evict it.
   - load(name, uid) -> { data, etag, savedAt } or null (none, other user, or older than
     MAX_AGE_DAYS: the whole store is then wiped).
   - save(name, uid, data, etag); touch(name, uid) when the server confirmed the data (304).
   - clearAll(): logout, loss of role (401/403).

   Every failure (IndexedDB missing or blocked, private window, quota) only means "no
   offline copy": the page then behaves as online-only. Calls never reject. */
(function () {
  "use strict";

  const DB_NAME = "alj-offline";
  const DB_VERSION = 1;
  const MAX_AGE_DAYS = 30;  // plan O4: limits what a lost phone exposes
  const MAX_AGE_MS = MAX_AGE_DAYS * 24 * 3600 * 1000;
  const LEGACY_PREFIX = "alj_snapshot:";  // phase 0-4 snapshots in localStorage

  let dbPromise = null;

  function openDb() {
    if (!dbPromise) {
      dbPromise = new Promise(resolve => {
        let req;
        try { req = indexedDB.open(DB_NAME, DB_VERSION); } catch (e) { resolve(null); return; }
        req.onupgradeneeded = () => {
          const db = req.result;
          if (!db.objectStoreNames.contains("resources")) db.createObjectStore("resources", { keyPath: "name" });
          if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta", { keyPath: "key" });
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
        req.onblocked = () => resolve(null);
      });
    }
    return dbPromise;
  }

  /* Runs fn(store) in one transaction; resolves with the result of the last request
     (or null on any failure). */
  async function run(storeName, mode, fn) {
    const db = await openDb();
    if (!db) return null;
    return new Promise(resolve => {
      try {
        const tx = db.transaction(storeName, mode);
        const req = fn(tx.objectStore(storeName));
        tx.oncomplete = () => resolve(req ? req.result : null);
        tx.onerror = tx.onabort = () => resolve(null);
      } catch (e) { resolve(null); }
    });
  }

  const get = (storeName, key) => run(storeName, "readonly", s => s.get(key));
  const put = (storeName, value) => run(storeName, "readwrite", s => s.put(value));

  function legacyStorage() {
    try { return window.localStorage; } catch (e) { return null; }
  }

  /* Old snapshots of this user go into the store, every old key is removed. */
  async function migrateLegacy(uid) {
    const ls = legacyStorage();
    if (!ls) return;
    let entries = [];
    try {
      for (let i = 0; i < ls.length; i++) {
        const k = ls.key(i);
        if (k && k.startsWith(LEGACY_PREFIX)) entries.push([k, ls.getItem(k)]);
      }
    } catch (e) { return; }
    for (const [k, raw] of entries) {
      try {
        const v = JSON.parse(raw || "null");
        if (v && v.uid === uid && !(await get("resources", k.slice(LEGACY_PREFIX.length)))) {
          await put("resources", { name: k.slice(LEGACY_PREFIX.length), uid, savedAt: v.savedAt, etag: null, data: v.data });
        }
      } catch (e) { /* unreadable: dropped */ }
      try { ls.removeItem(k); } catch (e) { /* blocked storage */ }
    }
  }

  async function start(uid) {
    if (!uid) return;
    const owner = await get("meta", "owner");
    if (owner && owner.uid !== uid) await clearAll();  // another account signs in on this phone
    await put("meta", { key: "owner", uid });
    await migrateLegacy(uid);
    try {
      if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
    } catch (e) { /* not supported */ }
  }

  async function load(name, uid) {
    if (!uid) return null;
    const rec = await get("resources", name);
    if (!rec || rec.uid !== uid) return null;
    if (!(Date.now() - rec.savedAt <= MAX_AGE_MS)) {
      await clearAll();
      return null;
    }
    return { data: rec.data, etag: rec.etag || null, savedAt: rec.savedAt };
  }

  async function save(name, uid, data, etag) {
    if (!uid) return;
    await put("resources", { name, uid, savedAt: Date.now(), etag: etag || null, data });
  }

  async function touch(name, uid) {
    const rec = await get("resources", name);
    if (rec && rec.uid === uid) await put("resources", Object.assign(rec, { savedAt: Date.now() }));
  }

  async function clearAll() {
    await run("resources", "readwrite", s => s.clear());
    await run("meta", "readwrite", s => s.clear());
    const ls = legacyStorage();
    try {
      const keys = [];
      for (let i = 0; ls && i < ls.length; i++) {
        const k = ls.key(i);
        if (k && k.startsWith(LEGACY_PREFIX)) keys.push(k);
      }
      keys.forEach(k => ls.removeItem(k));
    } catch (e) { /* nothing stored */ }
  }

  window.ALJStore = Object.freeze({ start, load, save, touch, clearAll, MAX_AGE_DAYS });
})();
