/* Data of a screen kept up to date by polling the API (lib/sync.ts): useSyncedResource(name, url, { offline }),
   plan decision D2. Online mode only for now: nothing is kept on the device, the data lives as long as the screen.
   The offline mode (IndexedDB copy for the directory, alj-store.js) comes with the directory (plan phase 9).

   url may change (another season): the poll of the former url is stopped, its late answers dropped, and data goes back
   to null until the new one answers. A null url polls nothing. The poll stops with the component (or effect scope),
   and on a 401 (signed out). */
import { getCurrentScope, inject, onScopeDispose, readonly, ref, shallowRef, toValue, watch, type MaybeRefOrGetter, type Ref } from "vue";
import { API_KEY, type ApiFetch } from "../lib/api";
import { poll, type Poll, type PollInfo, type PollStatus } from "../lib/sync";

/** loading: no answer yet for this url; the others: the last poll's outcome (lib/sync.ts PollStatus). */
export type SyncState = "loading" | PollStatus;

export interface SyncedResourceOptions {
  /** Online only: member data is not kept on this route (plan D2). */
  offline: false;
  intervalMs?: number;
  /** Defaults to the app's apiFetch (API_KEY), with the user's token. */
  fetch?: ApiFetch;
}

export interface SyncedResource<T> {
  /** Last data received for the current url, null before the first answer. */
  data: Readonly<Ref<T | null>>;
  state: Readonly<Ref<SyncState>>;
  /** HTTP status of the last refused poll (404, 403…), null otherwise. */
  httpStatus: Readonly<Ref<number | null>>;
  /** When the last poll answered (changed or not). */
  checkedAt: Readonly<Ref<Date | null>>;
  /** Loads now, e.g. right after the user's own write. */
  refresh(): Promise<void>;
  stop(): void;
}

export function useSyncedResource<T>(name: string, url: MaybeRefOrGetter<string | null>, options: SyncedResourceOptions): SyncedResource<T> {
  const fetchFn = options.fetch ?? inject(API_KEY);
  if (!fetchFn) throw new Error(`useSyncedResource(${name}): no API fetch provided`);
  const data = shallowRef<T | null>(null);
  const state = ref<SyncState>("loading");
  const httpStatus = ref<number | null>(null);
  const checkedAt = ref<Date | null>(null);
  let current: Poll | null = null;
  let stopped = false;

  function onStatus(status: PollStatus, info: PollInfo): void {
    state.value = status;
    httpStatus.value = info.status ?? null;
    if (status === "ok") checkedAt.value = new Date();
    if (info.status === 401) stop();  // signed out: the session watcher shows the sign-in gate
  }

  function start(target: string | null): void {
    current?.stop();
    current = null;
    data.value = null;
    state.value = "loading";
    httpStatus.value = null;
    if (!target || stopped) return;
    current = poll<T>(target, {
      fetch: fetchFn!,
      intervalMs: options.intervalMs,
      onData: (value) => {
        data.value = value;
      },
      onStatus,
    });
  }

  function stop(): void {
    stopped = true;
    current?.stop();
    current = null;
  }

  watch(() => toValue(url), start, { immediate: true });
  if (getCurrentScope()) onScopeDispose(stop);

  return {
    data,  // not readonly(): it would wrap every member in a proxy
    state: readonly(state),
    httpStatus: readonly(httpStatus),
    checkedAt: readonly(checkedAt),
    refresh: () => current?.refresh() ?? Promise.resolve(),
    stop,
  };
}
