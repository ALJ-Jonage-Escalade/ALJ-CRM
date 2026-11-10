/* The browser's localStorage for the preferences kept on the device (filters, panels, layouts). It can be missing or
   throw on access (private browsing, storage disabled): callers get undefined and keep the choice in memory only. */

export function localStorageOrNone(): Storage | undefined {
  try {
    return globalThis.localStorage ?? undefined;
  } catch {
    return undefined; // blocked storage
  }
}
