/* Start and end of the Google sign-in, on /competitions only (lib/oauth.ts: the OAuth redirect URI of the club), run
   once when the app starts (main.ts). Pages and the former pages ask for it with /competitions?login=1 after storing
   where to come back (sessionStorage "alj_after_login", composables/auth.ts login()).
   - back from Google: the access token of the URL fragment signs Firebase in;
   - dev: back from the Auth emulator's account picker;
   - ?login=1: the sign-in starts (Google, or the emulator's picker in dev).
   Then the page that asked is opened again. The session itself is then followed by composables/auth.ts. */
import type { InjectionKey, Ref } from "vue";
import { AFTER_LOGIN_KEY } from "./auth";
import { authorizeUrl, CALLBACK_PATH, newState, readFragment, STATE_KEY } from "../lib/oauth";

export interface SignInDeps {
  url: Pick<Location, "origin" | "pathname" | "search" | "hash">;
  storage: Pick<Storage, "getItem" | "setItem" | "removeItem">;
  /** Changes the address without loading it (history.replaceState). */
  replaceUrl(url: string): void;
  /** Loads another address (location.assign / location.replace). */
  navigate(url: string): void;
  emulator: boolean;
  signInWithToken(accessToken: string): Promise<void>;
  devSignIn(): Promise<void>;
  completeDevSignIn(): Promise<boolean>;
}

function errorText(e: unknown): string {
  const code = (e as { code?: unknown } | null)?.code;
  if (code === "auth/unauthorized-domain") {
    return "Domaine non autorisé : ajoutez l'adresse de ce site dans Firebase Authentication → Paramètres → Domaines autorisés.";
  }
  if (code === "auth/operation-not-allowed") {
    return "Le fournisseur Google n'est pas activé dans Firebase Authentication.";
  }
  if (code === "auth/network-request-failed") {
    return "Serveur injoignable : vérifiez la connexion réseau.";
  }
  return e instanceof Error && e.message ? e.message : "Connexion impossible.";
}

/** Runs the sign-in step the address asks for; resolves with the message of a failed sign-in, or null. */
export async function handleSignIn(deps: SignInDeps): Promise<string | null> {
  const { url, storage } = deps;
  if (url.pathname !== CALLBACK_PATH) {
    return null;
  }
  const here = url.pathname + url.search;

  // The page that asked for the sign-in (a path of this site only), unless it is this one
  const comeBack = (): void => {
    const back = storage.getItem(AFTER_LOGIN_KEY) ?? "";
    storage.removeItem(AFTER_LOGIN_KEY);
    if (/^\/[^/\\]/.test(back) && back !== here) {
      deps.navigate(back);
    }
  };

  try {
    if (url.hash.length > 1) {
      const back = readFragment(url.hash, storage.getItem(STATE_KEY));
      if (back) {
        deps.replaceUrl(here); // the token does not stay in the address (history, bookmarks)
        storage.removeItem(STATE_KEY);
        if ("error" in back) {
          return back.error;
        }
        await deps.signInWithToken(back.token);
        comeBack();
        return null;
      }
    }
    if (deps.emulator && (await deps.completeDevSignIn())) {
      comeBack();
      return null;
    }
    if (new URLSearchParams(url.search).get("login") === "1") {
      deps.replaceUrl(url.pathname);
      if (deps.emulator) {
        await deps.devSignIn();
      } else {
        const state = newState();
        storage.setItem(STATE_KEY, state);
        deps.navigate(authorizeUrl(url.origin, state));
      }
    }
  } catch (e) {
    console.error("Connexion :", e);
    return errorText(e);
  }
  return null;
}

/** The message of a failed sign-in, shown by the competitions page (provided by main.ts). */
export const SIGN_IN_ERROR_KEY: InjectionKey<Readonly<Ref<string | null>>> = Symbol("sign-in-error");
