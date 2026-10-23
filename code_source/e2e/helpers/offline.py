"""The offline copy of the app (IndexedDB "alj-offline", frontend/src/lib/store.ts, same database as the former pages'
web/shared/alj-store.js), read and changed from the page under test."""
from playwright.sync_api import Page

from helpers.data import eventually

_RECORD = """async (name) => new Promise(resolve => {
  const req = indexedDB.open("alj-offline");
  req.onerror = () => resolve(null);
  req.onsuccess = () => {
    const db = req.result;
    if (!db.objectStoreNames.contains("resources")) { db.close(); resolve(null); return; }
    const get = db.transaction("resources").objectStore("resources").get(name);
    get.onsuccess = () => { db.close(); resolve(get.result || null); };
    get.onerror = () => { db.close(); resolve(null); };
  };
})"""

_AGE = """async ([name, days]) => new Promise((resolve, reject) => {
  const req = indexedDB.open("alj-offline");
  req.onsuccess = () => {
    const db = req.result;
    const tx = db.transaction(["resources", "meta"], "readwrite");
    const resources = tx.objectStore("resources");
    const get = resources.get(name);
    get.onsuccess = () => resources.put(Object.assign(get.result, { savedAt: Date.now() - days * 24 * 3600 * 1000 }));
    tx.objectStore("meta").delete("confirmed:" + name);
    tx.oncomplete = () => { db.close(); resolve(); };
    tx.onerror = () => reject(tx.error);
  };
  req.onerror = () => reject(req.error);
})"""


_NAMES = """async () => new Promise(resolve => {
  const req = indexedDB.open("alj-offline");
  req.onerror = () => resolve([]);
  req.onsuccess = () => {
    const db = req.result;
    if (!db.objectStoreNames.contains("resources")) { db.close(); resolve([]); return; }
    const keys = db.transaction("resources").objectStore("resources").getAllKeys();
    keys.onsuccess = () => { db.close(); resolve(keys.result); };
    keys.onerror = () => { db.close(); resolve([]); };
  };
})"""


def resource_names(page: Page) -> list:
    """Names of every copy kept on the device."""
    return page.evaluate(_NAMES)


def record(page: Page, name: str):
    """The stored record {name, uid, savedAt, etag, data…}, or None."""
    return page.evaluate(_RECORD, name)


def stored(page: Page, name: str):
    rec = record(page, name)
    return rec["data"] if rec else None


def wait_stored(page: Page, name: str, check=lambda data: True, timeout=None):
    """The page saves after rendering: retried until the record is there and passes `check`."""
    def ready():
        data = stored(page, name)
        assert data is not None and check(data), data
        return data
    return eventually(ready, timeout=timeout)


def age(page: Page, name: str, days: int) -> None:
    """Makes the record `days` old (and forgets the server's later confirmations of it)."""
    page.evaluate(_AGE, [name, days])


_PUT = """async ([store, value]) => new Promise((resolve, reject) => {
  const req = indexedDB.open("alj-offline");
  req.onsuccess = () => {
    const db = req.result;
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).put(value);
    tx.oncomplete = () => { db.close(); resolve(); };
    tx.onerror = () => reject(tx.error);
  };
  req.onerror = () => reject(req.error);
})"""

_OWNER = """async () => new Promise(resolve => {
  const req = indexedDB.open("alj-offline");
  req.onerror = () => resolve(null);
  req.onsuccess = () => {
    const db = req.result;
    const get = db.transaction("meta").objectStore("meta").get("owner");
    get.onsuccess = () => { db.close(); resolve(get.result ? get.result.uid : null); };
    get.onerror = () => { db.close(); resolve(null); };
  };
})"""

_QUEUED = """async () => new Promise(resolve => {
  const req = indexedDB.open("alj-offline");
  req.onerror = () => resolve([]);
  req.onsuccess = () => {
    const db = req.result;
    const all = db.transaction("outbox").objectStore("outbox").getAll();
    all.onsuccess = () => { db.close(); resolve(all.result); };
    all.onerror = () => { db.close(); resolve([]); };
  };
})"""


def owner(page: Page) -> str:
    """Firebase uid of the account the store belongs to (written once signed in)."""
    def claimed():
        uid = page.evaluate(_OWNER)
        assert uid, "store not claimed yet"
        return uid
    return eventually(claimed)


def put_record(page: Page, record: dict) -> None:
    """A copy as the former pages' alj-store.js wrote it ({name, uid, savedAt, etag, data}, no url)."""
    page.evaluate(_PUT, ["resources", record])


def put_queued(page: Page, entry: dict) -> None:
    """A change in the outbox, as the former phone page queued it."""
    page.evaluate(_PUT, ["outbox", entry])


def queued(page: Page) -> list:
    return page.evaluate(_QUEUED)
