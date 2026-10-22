/** Calls to the API with the user's Firebase ID token; one retry with a fresh token on 401. */
import type { InjectionKey } from "vue";
import { firebaseAuth } from "./firebase";

export type ApiFetch = (url: string, init?: RequestInit) => Promise<Response>;
/** ID token of the signed-in user (null when signed out); forceRefresh asks Firebase for a new one. */
export type TokenSource = (forceRefresh: boolean) => Promise<string | null>;

export function createApiFetch(getToken: TokenSource, fetchImpl: typeof fetch = (...args) => fetch(...args)): ApiFetch {
  return async (url, init = {}) => {
    const send = async (forceRefresh: boolean): Promise<[Response, boolean]> => {
      const headers = new Headers(init.headers);
      const token = await getToken(forceRefresh);
      if (token) headers.set("Authorization", `Bearer ${token}`);
      return [await fetchImpl(url, { ...init, headers }), token !== null];
    };
    const [res, sentToken] = await send(false);
    if (res.status !== 401 || !sentToken) return res;
    return (await send(true))[0];
  };
}

export const apiFetch: ApiFetch = createApiFetch(async (forceRefresh) => {
  const user = firebaseAuth().currentUser;
  return user ? user.getIdToken(forceRefresh) : null;
});

/** Provided by main.ts; the components' tests provide a fake. */
export const API_KEY: InjectionKey<ApiFetch> = Symbol("api");
