/* Who is signed in and with which role.

   Firebase keeps the session; the role always comes from GET /api/me (the server decides).
   Sign-in goes through the competitions page, whose Google OAuth redirect URI is the only one
   registered: it signs in (emulator account picker in dev), then returns to the page stored in
   sessionStorage "alj_after_login" (same flow as web/shared/alj-core.js). */
import { onAuthStateChanged, signOut } from "@firebase/auth";
import { readonly, ref, type InjectionKey, type Ref } from "vue";
import { apiFetch } from "../lib/api";
import { ApiError, errorFromBody, NETWORK_MESSAGE } from "../lib/client";
import { firebaseAuth } from "../lib/firebase";
import { isRole, type Role } from "../lib/roles";

export interface SessionUser {
  uid: string;
  email: string;
}

export type AuthState =
  | { status: "loading" }
  | { status: "signedOut" }
  /** `invitationExpiredAt`: without a role, when this address's invitation ran out (unset: never invited). */
  | { status: "signedIn"; user: SessionUser; role: Role; invitationExpiredAt?: string }
  /** Signed in, but the server could not tell the role (offline: the network is down; server error, token refused). */
  | { status: "error"; user: SessionUser; message: string; offline: boolean };

export interface AuthDeps {
  /** Calls back with the current user now and on every change; returns the unsubscribe function. */
  onUserChange(callback: (user: SessionUser | null) => void): () => void;
  fetchMe(): Promise<Response>;
  signOut(): Promise<void>;
  storage: Pick<Storage, "setItem">;
  navigate(url: string): void;
  currentPath(): string;
  /** Calls back when the network comes back (an unverified role is asked again); returns the unsubscribe function. */
  onNetworkBack?(callback: () => void): () => void;
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
export const AFTER_LOGIN_STORAGE = "alj_after_login";

const UNEXPECTED_ANSWER = "Réponse inattendue du serveur.";

/** The signed-in account as GET /api/me describes it. */
interface MeAnswer {
  email: string;
  role: Role;
  invitationExpiredAt?: string;
}

/** The account of GET /api/me; an ApiError (the client's messages) for a refusal or an unexpected answer. */
async function readMe(res: Response): Promise<MeAnswer> {
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    // 503: the access list could not be read: the role stays unchecked (never "no access"), the server says why
    throw errorFromBody(res.status, body, res.status === 503 ? "Rôle non vérifiable pour le moment." : undefined);
  }
  const body = (await res.json()) as { email?: unknown; role?: unknown; invitation_expired_at?: unknown };
  const role = body.role;
  if (!isRole(role)) {
    throw new ApiError(res.status, "unexpected", UNEXPECTED_ANSWER);
  }
  const email = typeof body.email === "string" ? body.email : "";
  return typeof body.invitation_expired_at === "string"
    ? { email, role, invitationExpiredAt: body.invitation_expired_at }
    : { email, role };
}

/** fetch rejects with a TypeError offline; Firebase, renewing the token, with auth/network-request-failed. */
function isNetworkError(e: unknown): boolean {
  return e instanceof TypeError || (e as { code?: unknown } | null)?.code === "auth/network-request-failed";
}

function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    return e.message;
  }
  if (isNetworkError(e)) {
    return NETWORK_MESSAGE;
  }
  return UNEXPECTED_ANSWER; // e.g. a body that is not JSON
}

export function createAuth(deps: AuthDeps): Auth {
  const state = ref<AuthState>({ status: "loading" });
  let current: SessionUser | null = null;
  let generation = 0; // an answer for a previous user (or an older request) is dropped

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
      const signedInUser = { uid: user.uid, email: me.email || user.email };
      next = me.invitationExpiredAt
        ? { status: "signedIn", user: signedInUser, role: me.role, invitationExpiredAt: me.invitationExpiredAt }
        : { status: "signedIn", user: signedInUser, role: me.role };
    } catch (e) {
      next = { status: "error", user, message: errorMessage(e), offline: isNetworkError(e) };
    }
    if (mine === generation) {
      state.value = next;
    }
  }

  const stopUser = deps.onUserChange((user) => void resolve(user));
  const stopNetwork = deps.onNetworkBack?.(() => {
    if (state.value.status === "error") {
      void resolve(current);
    }
  });

  return {
    state: readonly(state),
    login() {
      deps.storage.setItem(AFTER_LOGIN_STORAGE, deps.currentPath());
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
    stop() {
      stopUser();
      stopNetwork?.();
    },
  };
}

export const AUTH_KEY: InjectionKey<Auth> = Symbol("auth");

let shared: Auth | null = null;

/** The app's session (Firebase + /api/me), created once. */
export function sharedAuth(): Auth {
  if (shared) {
    return shared;
  }
  const auth = firebaseAuth();
  shared = createAuth({
    onUserChange: (callback) => onAuthStateChanged(auth, (u) => callback(u ? { uid: u.uid, email: u.email ?? "" } : null)),
    fetchMe: () => apiFetch("/api/me"),
    signOut: () => signOut(auth),
    storage: sessionStorage,
    navigate: (url) => location.assign(url),
    currentPath: () => location.pathname + location.search,
    onNetworkBack: (callback) => {
      window.addEventListener("online", callback);
      return () => window.removeEventListener("online", callback);
    },
  });
  return shared;
}
