/* Google sign-in of the club, unchanged from the former competitions page: implicit OAuth (access token in the URL
   fragment) on the same origin, then Firebase signInWithCredential. It avoids the redirect through firebaseapp.com,
   whose cross-site storage is blocked (Firefox ETP, private windows, installed PWA). The redirect URI is /competitions,
   the only one registered for the OAuth client: the sign-in starts and ends there (composables/signIn.ts). */

const AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
export const OAUTH_CLIENT_ID = "796572126711-npcue84vd52prmtjik0bdp6ng6ggpie8.apps.googleusercontent.com";
const SCOPES = "openid email profile";
export const STATE_KEY = "alj_oauth_state";
export const CALLBACK_PATH = "/competitions";

/** A random state, checked on the way back (CSRF). */
export function newState(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}

export function authorizeUrl(origin: string, state: string): string {
  const params = new URLSearchParams({
    client_id: OAUTH_CLIENT_ID,
    redirect_uri: origin + CALLBACK_PATH,
    response_type: "token",
    scope: SCOPES,
    state,
    prompt: "select_account",
  });
  return `${AUTH_URL}?${params}`;
}

/** What Google sent back in the URL fragment: nothing (null), an access token, or an error to show. */
export type OauthReturn = null | { token: string } | { error: string };

export function readFragment(hash: string, expectedState: string | null): OauthReturn {
  if (!hash || hash.length < 2) return null;
  const params = new URLSearchParams(hash.slice(1));
  if (params.get("error")) return { error: `Connexion Google refusée : ${params.get("error")}` };
  const token = params.get("access_token");
  if (!token) return null;
  const state = params.get("state");
  if (!state || state !== expectedState) return { error: "Session de connexion invalide — cliquez à nouveau sur « Se connecter »." };
  return { token };
}
