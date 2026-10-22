/* Who is signed in and with which role.

   Firebase keeps the session; the role always comes from GET /api/me (the server decides).
   Sign-in goes through the competitions page, whose Google OAuth redirect URI is the only one
   registered: it signs in (emulator account picker in dev), then returns to the page stored in
   sessionStorage "alj_after_login" (same flow as web/shared/alj-core.js). */
import { onAuthStateChanged, signOut } from "@firebase/auth";
import { readonly, ref, type InjectionKey, type Ref } from "vue";
import { apiFetch } from "../lib/api";
import { firebaseAuth } from "../lib/firebase";
import type { Role } from "../lib/roles";

export interface SessionUser {
  uid: string;
  email: string;
}

export type AuthState =
  | { status: "loading" }
  | { status: "signedOut" }
  | { status: "signedIn"; user: SessionUser; role: Role }
  /** Signed in, but the server could not tell the role (offline, server error, token refused). */
  | { status: "error"; user: SessionUser; message: string };

export interface AuthDeps {
  /** Calls back with the current user now and on every change; returns the unsubscribe function. */
  onUserChange(callback: (user: SessionUser | null) => void): () => void;
  fetchMe(): Promise<Response>;
  signOut(): Promise<void>;
  storage: Pick<Storage, "setItem">;
  navigate(url: string): void;
  currentPath(): string;
}

export interface Auth {
  state: Readonly<Ref<AuthState>>;
  login(): void;
  logout(): Promise<void>;
  /** Asks the server for the role again (after an error). */
  retry(): Promise<void>;
  stop(): void;
}

export const LOGIN_URL = "/competitions?login=1";
export const AFTER_LOGIN_KEY = "alj_after_login";
const ROLES: readonly Role[] = ["admin", "coach", "readonly", null];

/** A refusal or an unexpected answer of /api/me, with the message shown to the user. */
class MeError extends Error {}

async function readMe(res: Response): Promise<{ email: string; role: Role }> {
  if (res.status === 401) throw new MeError("Session refusée par le serveur : reconnectez-vous.");
  if (!res.ok) throw new MeError(`Le serveur ne répond pas correctement (erreur ${res.status}).`);
  const body = (await res.json()) as { email?: unknown; role?: unknown };
  const role = ROLES.find((r) => r === body.role);
  if (role === undefined) throw new MeError("Réponse inattendue du serveur.");
  return { email: typeof body.email === "string" ? body.email : "", role };
}

function errorMessage(e: unknown): string {
  if (e instanceof MeError) return e.message;
  if (e instanceof TypeError) return "Serveur injoignable : vérifiez la connexion réseau.";  // fetch rejects offline
  return "Réponse inattendue du serveur.";  // e.g. a body that is not JSON
}

export function createAuth(deps: AuthDeps): Auth {
  const state = ref<AuthState>({ status: "loading" });
  let current: SessionUser | null = null;
  let generation = 0;  // an answer for a previous user (or an older request) is dropped

  async function resolve(user: SessionUser | null): Promise<void> {
    const mine = ++generation;
    current = user;
    if (!user) {
      state.value = { status: "signedOut" };
      return;
    }
    let next: AuthState;
    try {
      const me = await readMe(await deps.fetchMe());
      next = { status: "signedIn", user: { uid: user.uid, email: me.email || user.email }, role: me.role };
    } catch (e) {
      next = { status: "error", user, message: errorMessage(e) };
    }
    if (mine === generation) state.value = next;
  }

  const stop = deps.onUserChange((user) => void resolve(user));

  return {
    state: readonly(state),
    login() {
      deps.storage.setItem(AFTER_LOGIN_KEY, deps.currentPath());
      deps.navigate(LOGIN_URL);
    },
    async logout() {
      try {
        await deps.signOut();
      } catch (e) {
        console.warn("Déconnexion :", e);
      }
    },
    retry: () => resolve(current),
    stop,
  };
}

export const AUTH_KEY: InjectionKey<Auth> = Symbol("auth");

let shared: Auth | null = null;

/** The app's session (Firebase + /api/me), created once. */
export function sharedAuth(): Auth {
  if (shared) return shared;
  const auth = firebaseAuth();
  shared = createAuth({
    onUserChange: (callback) => onAuthStateChanged(auth, (u) => callback(u ? { uid: u.uid, email: u.email ?? "" } : null)),
    fetchMe: () => apiFetch("/api/me"),
    signOut: () => signOut(auth),
    storage: sessionStorage,
    navigate: (url) => location.assign(url),
    currentPath: () => location.pathname + location.search,
  });
  return shared;
}
