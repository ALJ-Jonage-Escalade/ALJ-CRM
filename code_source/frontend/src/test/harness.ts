/* Shared pieces of the components' tests: fake API answers, a fake session, the provided services, and a wait for
   IndexedDB (fake-indexeddb) to finish. Test code only (vitest runs *.test.ts; this module is imported by them). */
import { flushPromises } from "@vue/test-utils";
import { vi } from "vitest";
import { isRef, ref, type Ref } from "vue";
import { AUTH_KEY, type Auth, type AuthState } from "../composables/auth";
import { API_KEY, type ApiFetch } from "../lib/api";
import { CLIENT_KEY, createApiClient } from "../lib/client";

/** Base URL of the fake API client. */
export const TEST_ORIGIN = "http://alj.test";

/** A JSON answer of the API, with an ETag when given. */
export function json(body: unknown, status = 200, etag?: string): Response {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (etag) {
    headers.ETag = etag;
  }
  return new Response(JSON.stringify(body), { status, headers });
}

/** A session in the given state (or following the given ref), its actions recorded. */
export function fakeAuth(state: AuthState | Ref<AuthState>): Auth {
  return {
    state: isRef(state) ? state : ref(state),
    login: vi.fn(),
    logout: vi.fn(async () => {}),
    retry: vi.fn(async () => {}),
    stop: vi.fn(),
  };
}

/** What main.ts provides to the pages, over a fake fetch: the session, the API fetch and the typed client. */
export function provided(auth: Auth, api: ApiFetch): Record<symbol, unknown> {
  return { [AUTH_KEY]: auth, [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, TEST_ORIGIN) };
}

/** Waits until IndexedDB (fake-indexeddb, which schedules its work with setImmediate) and the renders it triggers are
    done: rounds of promises and setImmediate until two rounds in a row schedule nothing new. */
export async function settle(maxRounds = 100): Promise<void> {
  const original = globalThis.setImmediate;
  let scheduled = 0;
  const counting = ((...args: Parameters<typeof setImmediate>) => {
    scheduled++;
    return original(...args);
  }) as typeof setImmediate;
  globalThis.setImmediate = counting;
  try {
    for (let quietRounds = 0, round = 0; quietRounds < 2 && round < maxRounds; round++) {
      scheduled = 0;
      await flushPromises();
      await new Promise((resolve) => original(resolve));
      quietRounds = scheduled === 0 ? quietRounds + 1 : 0;
    }
  } finally {
    globalThis.setImmediate = original;
  }
}
