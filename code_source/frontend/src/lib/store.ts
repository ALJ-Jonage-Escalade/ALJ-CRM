/* Offline copy of the data received from the API, in IndexedDB (TypeScript port of the former pages' alj-store.js;
   plan decision D2: same behaviour, no rewrite). Same database as those pages ("alj-offline": resources, meta,
   outbox), so what they stored is read and wiped here.

   - start(uid): call once signed in. Wipes the store when another user owned it, moves the old localStorage
     snapshots (alj_snapshot:*) in, and asks the browser not to evict it. Calls for the same user share one start.
   - load(name, uid) -> { data, etag, savedAt, url } or null (none, other user, or older than MAX_AGE_DAYS: the whole
     store is then wiped).
   - save(name, uid, data, etag, url); touch(name, uid) when the server confirmed the data (304): only a small
     "confirmed:<name>" record in meta is written, not the data again. url: where the data came from (a resource
     whose url changes, e.g. another season, keeps one copy: the last one).
   - Outbox of the changes made offline, sent when the network comes back: queue(uid, entry) adds or replaces
     entry.key, queued(uid) lists this user's entries, unqueue(key) removes one.
   - clearAll(): logout, loss of role (401/403); the outbox goes too. Writes of a start/save/touch/queue begun before
     it are dropped, so a cleared store is not filled again by work still in progress.

   Every failure (IndexedDB missing or blocked, private window, quota) only means "no offline copy": the page then
   behaves as online only. Calls never reject. */
import type { InjectionKey } from "vue";
import { localStorageOrNone } from "./localStorage";
import { plural } from "./text";

const DB_NAME = "alj-offline";
const DB_VERSION = 2; // 2: outbox
export const MAX_AGE_DAYS = 30; // limits what a lost phone exposes
const MAX_AGE_MS = MAX_AGE_DAYS * 24 * 3600 * 1000;
/* Snapshots of the first phone pages, in localStorage. Remove LEGACY_PREFIX, legacyKeys and migrateLegacy after
   2026-11-24: the former pages were removed on 2026-10-25 and every copy expires after MAX_AGE_DAYS (30), so none is left to move. */
const LEGACY_PREFIX = "alj_snapshot:";
const OPEN_TIMEOUT_MS = 3000; // some WebKit versions never answer indexedDB.open

export interface Stored<T = unknown> {
  data: T;
  etag: string | null;
  savedAt: number;
  url: string | null;
}

export interface OutboxEntry {
  key: string;
  [field: string]: unknown;
}

export interface OfflineStore {
  start(uid: string | null): Promise<void>;
  load<T>(name: string, uid: string | null): Promise<Stored<T> | null>;
  save(name: string, uid: string | null, data: unknown, etag: string | null, url?: string | null): Promise<void>;
  touch(name: string, uid: string | null): Promise<void>;
  queue(uid: string | null, entry: OutboxEntry): Promise<void>;
  queued(uid: string | null): Promise<OutboxEntry[]>;
  unqueue(key: string): Promise<void>;
  clearAll(): Promise<void>;
}

export interface StoreDeps {
  indexedDB?: IDBFactory;
  /** The old snapshots' storage (localStorage); undefined when blocked. */
  storage?: Storage;
  now?: () => number;
  persist?: () => void;
}

interface ResourceRecord {
  name: string;
  uid: string;
  savedAt: number;
  etag: string | null;
  url?: string | null;
  data: unknown;
}

type StoreName = "resources" | "meta" | "outbox";

export function createOfflineStore(deps: StoreDeps = {}): OfflineStore {
  const now = deps.now ?? Date.now;
  let dbPromise: Promise<IDBDatabase | null> | null = null;
  let epoch = 0; // bumped by clearAll: writes started before it are dropped
  let started: { uid: string; epoch: number; done: Promise<void> } | null = null;

  function openDb(): Promise<IDBDatabase | null> {
    dbPromise ??= new Promise((resolve) => {
      let req: IDBOpenDBRequest;
      try {
        if (!deps.indexedDB) {
          throw new Error("no IndexedDB");
        }
        req = deps.indexedDB.open(DB_NAME, DB_VERSION);
      } catch {
        resolve(null);
        return;
      }
      req.onupgradeneeded = () => {
        const db = req.result;
        for (const [store, keyPath] of [
          ["resources", "name"],
          ["meta", "key"],
          ["outbox", "key"],
        ] as const) {
          if (!db.objectStoreNames.contains(store)) {
            db.createObjectStore(store, { keyPath });
          }
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
      req.onblocked = () => resolve(null);
      setTimeout(() => resolve(null), OPEN_TIMEOUT_MS); // no answer: online only
    });
    return dbPromise;
  }

  /* Runs fn(store) in one transaction; resolves with the result of the last request (or null on any failure). */
  async function run<R>(
    storeName: StoreName,
    mode: IDBTransactionMode,
    fn: (s: IDBObjectStore) => IDBRequest<R> | null,
  ): Promise<R | null> {
    const db = await openDb();
    if (!db) {
      return null;
    }
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(storeName, mode);
        const req = fn(tx.objectStore(storeName));
        tx.oncomplete = () => resolve(req ? req.result : null);
        tx.onerror = tx.onabort = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }

  const get = <R>(storeName: StoreName, key: string) => run<R>(storeName, "readonly", (s) => s.get(key));
  /* Write begun at epoch e: skipped once clearAll ran since. The check happens when the transaction is created, and
     IndexedDB runs readwrite transactions in creation order. */
  const put = (e: number, storeName: StoreName, value: object) => run(storeName, "readwrite", (s) => (e === epoch ? s.put(value) : null));

  function legacyKeys(): string[] {
    const ls = deps.storage;
    const keys: string[] = [];
    try {
      for (let i = 0; ls && i < ls.length; i++) {
        const k = ls.key(i);
        if (k?.startsWith(LEGACY_PREFIX)) {
          keys.push(k);
        }
      }
    } catch {
      // blocked storage: nothing to move
    }
    return keys;
  }

  /* Old snapshots of this user go into the store, every old key is removed. */
  async function migrateLegacy(uid: string, e: number): Promise<void> {
    const ls = deps.storage;
    if (!ls) {
      return;
    }
    for (const k of legacyKeys()) {
      try {
        const v = JSON.parse(ls.getItem(k) || "null") as { uid?: unknown; savedAt?: unknown; data?: unknown } | null;
        const name = k.slice(LEGACY_PREFIX.length);
        if (v && v.uid === uid && !(await get("resources", name))) {
          await put(e, "resources", { name, uid, savedAt: v.savedAt, etag: null, data: v.data });
        }
      } catch {
        // unreadable: dropped
      }
      if (e !== epoch) {
        return;
      } // cleared meanwhile: clearAll removes the old keys itself
      try {
        ls.removeItem(k);
      } catch {
        // blocked storage
      }
    }
  }

  async function doStart(uid: string): Promise<void> {
    let e = epoch;
    const owner = await get<{ uid: string }>("meta", "owner");
    if (owner && owner.uid !== uid) {
      await clearAll(); // another account signs in on this device
      if (e + 1 !== epoch) {
        return;
      } // cleared by someone else too (logout): stop here
      e = epoch;
    }
    await put(e, "meta", { key: "owner", uid });
    await migrateLegacy(uid, e);
    try {
      deps.persist?.();
    } catch {
      // not supported
    }
  }

  function start(uid: string | null): Promise<void> {
    if (!uid) {
      return Promise.resolve();
    }
    if (started && started.uid === uid && started.epoch === epoch) {
      return started.done;
    }
    const done = doStart(uid);
    started = { uid, epoch, done };
    return done;
  }

  async function load<T>(name: string, uid: string | null): Promise<Stored<T> | null> {
    if (!uid) {
      return null;
    }
    const rec = await get<ResourceRecord>("resources", name);
    if (!rec || rec.uid !== uid) {
      return null;
    }
    const confirmed = await get<{ uid: string; at: number }>("meta", `confirmed:${name}`);
    const savedAt = confirmed && confirmed.uid === uid ? Math.max(rec.savedAt, confirmed.at) : rec.savedAt;
    if (!(now() - savedAt <= MAX_AGE_MS)) {
      await clearAll();
      return null;
    }
    return { data: rec.data as T, etag: rec.etag || null, savedAt, url: rec.url ?? null };
  }

  async function save(name: string, uid: string | null, data: unknown, etag: string | null, url: string | null = null): Promise<void> {
    if (!uid) {
      return;
    }
    await put(epoch, "resources", { name, uid, savedAt: now(), etag: etag || null, url, data });
  }

  /* The data is not read nor rewritten: load() takes the later of the two dates. */
  async function touch(name: string, uid: string | null): Promise<void> {
    if (!uid) {
      return;
    }
    await put(epoch, "meta", { key: `confirmed:${name}`, uid, at: now() });
  }

  async function queue(uid: string | null, entry: OutboxEntry): Promise<void> {
    if (!uid || !entry?.key) {
      return;
    }
    await put(epoch, "outbox", { ...entry, uid });
  }

  async function queued(uid: string | null): Promise<OutboxEntry[]> {
    if (!uid) {
      return [];
    }
    const all = await run<OutboxEntry[]>("outbox", "readonly", (s) => s.getAll());
    return (all ?? []).filter((e) => e?.uid === uid);
  }

  async function unqueue(key: string): Promise<void> {
    await run("outbox", "readwrite", (s) => s.delete(key));
  }

  async function clearAll(): Promise<void> {
    epoch++;
    await run("resources", "readwrite", (s) => s.clear());
    await run("meta", "readwrite", (s) => s.clear());
    await run("outbox", "readwrite", (s) => s.clear());
    try {
      for (const k of legacyKeys()) {
        deps.storage?.removeItem(k);
      }
    } catch {
      // nothing stored
    }
  }

  return { start, load, save, touch, queue, queued, unqueue, clearAll };
}

/** Provided by main.ts (offlineStore()) and by the components' tests. */
export const STORE_KEY: InjectionKey<OfflineStore> = Symbol("offline-store");

let shared: OfflineStore | null = null;

/** The app's store, opened on first use (main.ts provides it). */
export function offlineStore(): OfflineStore {
  shared ??= createOfflineStore({
    indexedDB: globalThis.indexedDB,
    storage: localStorageOrNone(),
    persist: () => void navigator.storage?.persist?.().catch(() => {}),
  });
  return shared;
}

/** Confirmation asked before signing out with changes not sent yet (they are lost with the store). */
export function logoutWarning(n: number): string {
  return `${n} modification${plural(n)} faite${plural(n)} hors ligne pas encore envoyée${plural(n)} ser${plural(n, "ont", "a")} perdue${plural(n)}. Se déconnecter ?`;
}
