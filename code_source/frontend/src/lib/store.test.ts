import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it } from "vitest";
import { createOfflineStore, MAX_AGE_DAYS, type OfflineStore } from "./store";

const DAY = 24 * 3600 * 1000;

let idb: IDBFactory;
let clock: number;
let store: OfflineStore;

function newStore(): OfflineStore {
  return createOfflineStore({ indexedDB: idb, storage: localStorage, now: () => clock });
}

beforeEach(() => {
  idb = new IDBFactory();
  clock = Date.UTC(2026, 9, 1);
  localStorage.clear();
  store = newStore();
});

/** A record as web/shared/alj-store.js (the competitions page) writes it: no url. */
function writeAsFormerPage(record: object): Promise<void> {
  return new Promise((resolve, reject) => {
    const req = idb.open("alj-offline", 2);
    req.onupgradeneeded = () => {
      for (const [name, keyPath] of [
        ["resources", "name"],
        ["meta", "key"],
        ["outbox", "key"],
      ])
        req.result.createObjectStore(name!, { keyPath });
    };
    req.onsuccess = () => {
      const tx = req.result.transaction("resources", "readwrite");
      tx.objectStore("resources").put(record);
      tx.oncomplete = () => {
        req.result.close();
        resolve();
      };
      tx.onerror = () => reject(tx.error ?? new Error("transaction failed"));
    };
  });
}

describe("offline store", () => {
  it("loads what was saved, for the same user only", async () => {
    await store.start("u1");
    await store.save("directory", "u1", { n: 1 }, '"e1"', "/api/members");
    expect(await store.load("directory", "u1")).toEqual({ data: { n: 1 }, etag: '"e1"', savedAt: clock, url: "/api/members" });
    expect(await store.load("directory", "u2")).toBeNull();
    expect(await store.load("directory", null)).toBeNull();
    expect(await store.load("other", "u1")).toBeNull();
  });

  it("reads the records of the former page", async () => {
    await writeAsFormerPage({ name: "competitions", uid: "u1", savedAt: clock - DAY, etag: null, data: [1, 2] });
    expect(await store.load("competitions", "u1")).toEqual({ data: [1, 2], etag: null, savedAt: clock - DAY, url: null });
  });

  it("wipes everything when a copy is older than the age limit", async () => {
    await store.start("u1");
    await store.save("directory", "u1", { n: 1 }, null);
    clock += 2 * DAY;
    await store.save("competitions", "u1", [1], null);
    await store.queue("u1", { key: "k1" });
    clock += (MAX_AGE_DAYS - 1) * DAY;
    expect(await store.load("directory", "u1")).toBeNull(); // 31 days old
    expect(await store.load("competitions", "u1")).toBeNull();
    expect(await store.queued("u1")).toEqual([]);
  });

  it("keeps a copy the server confirmed (304) without writing it again", async () => {
    await store.save("directory", "u1", { n: 1 }, '"e1"');
    clock += 20 * DAY;
    await store.touch("directory", "u1");
    clock += 20 * DAY;
    expect((await store.load("directory", "u1"))?.savedAt).toBe(clock - 20 * DAY);
  });

  it("wipes the previous user's data when another account signs in", async () => {
    await store.start("u1");
    await store.save("directory", "u1", { n: 1 }, null);
    await store.queue("u1", { key: "k1" });
    const other = newStore(); // next visit
    await other.start("u2");
    expect(await other.load("directory", "u1")).toBeNull();
    expect(await other.queued("u1")).toEqual([]);
    await other.save("directory", "u2", { n: 2 }, null);
    await newStore().start("u2"); // same user again: kept
    expect((await other.load("directory", "u2"))?.data).toEqual({ n: 2 });
  });

  it("drops a write begun before clearAll", async () => {
    const saving = store.save("directory", "u1", { n: 1 }, null);
    const queuing = store.queue("u1", { key: "k1" });
    await store.clearAll();
    await Promise.all([saving, queuing]);
    expect(await store.load("directory", "u1")).toBeNull();
    expect(await store.queued("u1")).toEqual([]);
  });

  it("moves the old localStorage snapshots of the user in, and removes every old key", async () => {
    localStorage.setItem("alj_snapshot:competitions", JSON.stringify({ uid: "u1", savedAt: clock - DAY, data: [1] }));
    localStorage.setItem("alj_snapshot:coaches", JSON.stringify({ uid: "u2", savedAt: clock, data: [2] }));
    localStorage.setItem("alj_annuaire_filters", "{}");
    await store.start("u1");
    expect((await store.load("competitions", "u1"))?.data).toEqual([1]);
    expect(await store.load("coaches", "u2")).toBeNull();
    expect(Object.keys(localStorage)).toEqual(["alj_annuaire_filters"]);
  });

  it("keeps the outbox per user, one entry per key", async () => {
    await store.queue("u1", { key: "a", value: 1 });
    await store.queue("u1", { key: "a", value: 2 });
    await store.queue("u2", { key: "b", value: 3 });
    expect(await store.queued("u1")).toEqual([{ key: "a", value: 2, uid: "u1" }]);
    await store.unqueue("a");
    expect(await store.queued("u1")).toEqual([]);
    expect(await store.queued("u2")).toHaveLength(1);
  });

  it("behaves as online only without IndexedDB", async () => {
    const none = createOfflineStore({ storage: localStorage });
    await none.start("u1");
    await none.save("directory", "u1", { n: 1 }, null);
    expect(await none.load("directory", "u1")).toBeNull();
    expect(await none.queued("u1")).toEqual([]);
  });
});
