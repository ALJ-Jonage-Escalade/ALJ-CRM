/* Data of a screen kept up to date by polling the API (lib/sync.ts): useSyncedResource(name, url, { offline }),
   plan decision D2.
   - Online mode: nothing is kept on the device, the data lives as long as the screen.
   - Offline mode (the directory): the last answer is kept in IndexedDB (lib/store.ts) for its user; the copy is shown
     at once, before the first poll (which sends its ETag, so an unchanged copy costs a 304), and while the network is
     down. One copy per name: the copy of another url (another season) is not shown. A 401 or 403 wipes the store
     (role lost); logout and the 30-day limit are handled by the store and offline.ts.

   url may change (another season): the poll of the former url is stopped, its late answers dropped, and data goes back
   to null (or the offline copy of the new url) until the new one answers. A null url polls nothing. The poll stops with
   the component (or effect scope), and on a 401 (signed out). */
import { getCurrentScope, inject, onScopeDispose, readonly, ref, shallowRef, toValue, watch, type MaybeRefOrGetter, type Ref } from "vue";
import { API_KEY, type ApiFetch } from "../lib/api";
import { offlineStore, STORE_KEY, type OfflineStore } from "../lib/store";
import { poll, type Poll, type PollInfo, type PollStatus } from "../lib/sync";

/** loading: no answer yet for this url; the others: the last poll's outcome (lib/sync.ts PollStatus). */
export type SyncState = "loading" | PollStatus;

export interface SyncedResourceOptions<T> {
  /** false: member data that must not stay on the device (plan D2); true: the copy is kept (needs uid). */
  offline: boolean;
  /** Offline mode: the signed-in user, owner of the copy; null keeps nothing (signed out, not known yet). */
  uid?: MaybeRefOrGetter<string | null>;
  /** Applied to every answer before it is shown and kept: only what the screen needs stays on the device. */
  select?: (answer: unknown) => T;
  intervalMs?: number;
  /** Defaults to the app's apiFetch (API_KEY), with the user's token. */
  fetch?: ApiFetch;
  /** Defaults to the provided store (STORE_KEY), else the app's. */
  store?: OfflineStore;
}

export interface SyncedResource<T> {
  /** Last data received for the current url (or its offline copy), null before the first answer. */
  data: Readonly<Ref<T | null>>;
  state: Readonly<Ref<SyncState>>;
  /** HTTP status of the last refused poll (404, 403…), null otherwise. */
  httpStatus: Readonly<Ref<number | null>>;
  /** When the last poll answered (changed or not). */
  checkedAt: Readonly<Ref<Date | null>>;
  /** When the server last sent or confirmed the data shown: the offline copy's date until the server answers. */
  dataAt: Readonly<Ref<Date | null>>;
  /** Loads now, e.g. right after the user's own write. */
  refresh(): Promise<void>;
  /** Shows data the user just wrote (the write's answer) until the next poll brings the server's; kept in memory only. */
  set(value: T): void;
  stop(): void;
}

export function useSyncedResource<T>(
  name: string,
  url: MaybeRefOrGetter<string | null>,
  options: SyncedResourceOptions<T>,
): SyncedResource<T> {
  const fetchFn = options.fetch ?? inject(API_KEY);
  if (!fetchFn) throw new Error(`useSyncedResource(${name}): no API fetch provided`);
  const store = options.offline ? (options.store ?? inject(STORE_KEY, null) ?? offlineStore()) : null;
  const select = options.select ?? ((answer: unknown) => answer as T);
  const data = shallowRef<T | null>(null);
  const state = ref<SyncState>("loading");
  const httpStatus = ref<number | null>(null);
  const checkedAt = ref<Date | null>(null);
  const dataAt = ref<Date | null>(null);
  let current: Poll | null = null;
  let generation = 0; // a start for a former url or user, still reading the store, is dropped
  let stopped = false;

  async function start([target, uid]: readonly [string | null, string | null]): Promise<void> {
    const mine = ++generation;
    current?.stop();
    current = null;
    data.value = null;
    dataAt.value = null;
    state.value = "loading";
    httpStatus.value = null;
    if (!target || stopped) return;
    const owner = store ? uid : null;
    let etag: string | null = null;
    if (store && owner) {
      await store.start(owner);
      const copy = await store.load<T>(name, owner);
      if (mine !== generation || stopped) return;
      // No url: written by the former competitions page (alj-store.js), for the same fixed url
      if (copy && (copy.url === target || copy.url === null)) {
        data.value = copy.data;
        dataAt.value = new Date(copy.savedAt);
        etag = copy.etag;
      }
    }
    current = poll<unknown>(target, {
      fetch: fetchFn!,
      intervalMs: options.intervalMs,
      etag,
      onData: (answer, newEtag) => {
        const value = select(answer);
        data.value = value;
        if (store && owner) void store.save(name, owner, value, newEtag, target);
      },
      onStatus: (status, info) => {
        if (store && owner && status === "ok" && !info.changed) void store.touch(name, owner);
        onStatus(status, info);
      },
    });
  }

  function onStatus(status: PollStatus, info: PollInfo): void {
    state.value = status;
    httpStatus.value = info.status ?? null;
    if (status === "ok") checkedAt.value = dataAt.value = new Date();
    if (store && (info.status === 401 || info.status === 403)) {
      // Role lost: nothing kept on the device, this user's other copies included
      data.value = null;
      dataAt.value = null;
      void store.clearAll();
    }
    if (info.status === 401 || (store && info.status === 403)) stop(); // signed out: the session watcher shows the sign-in gate
  }

  function stop(): void {
    stopped = true;
    generation++;
    current?.stop();
    current = null;
  }

  // The same url and user again (the session answered once more): the poll goes on
  watch(
    () => [toValue(url), store ? (toValue(options.uid) ?? null) : null] as const,
    (next, previous) => {
      if (!previous || next[0] !== previous[0] || next[1] !== previous[1]) void start(next);
    },
    { immediate: true },
  );
  if (getCurrentScope()) onScopeDispose(stop);

  return {
    data, // not readonly(): it would wrap every member in a proxy
    state: readonly(state),
    httpStatus: readonly(httpStatus),
    checkedAt: readonly(checkedAt),
    dataAt: readonly(dataAt),
    refresh: () => current?.refresh() ?? Promise.resolve(),
    set: (value) => {
      if (current) data.value = value; // not for a former url, nor once stopped
    },
    stop,
  };
}
