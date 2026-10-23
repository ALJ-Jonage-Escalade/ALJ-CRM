/* Firebase only signs the user in: its ID token is sent to the API, which decides the rights.
   Same project and app name as the former pages (alj-firebase.js), so the session (IndexedDB) they left is kept:
   no new sign-in after the update. */
import { initializeApp } from "@firebase/app";
import {
  browserLocalPersistence, browserPopupRedirectResolver, connectAuthEmulator, getRedirectResult, GoogleAuthProvider,
  indexedDBLocalPersistence, initializeAuth, signInWithCredential, signInWithRedirect, type Auth,
} from "@firebase/auth";
import { isEmulator, runtime } from "./runtime";

const FIREBASE_CONFIG = Object.freeze({
  apiKey: "AIzaSyDtwH7A6XokZZjUcyoL83gx9ZjyuN4IJoQ",
  authDomain: "smart-amplifier-510811-n6.firebaseapp.com",
  projectId: "smart-amplifier-510811-n6",
  appId: "1:796572126711:web:a827fd60c313ba2c46f2f2",
});

let auth: Auth | null = null;

export function firebaseAuth(): Auth {
  if (auth) return auth;
  const app = initializeApp(isEmulator ? { ...FIREBASE_CONFIG, projectId: runtime.projectId } : FIREBASE_CONFIG);
  // No popup/redirect resolver by default: only the emulator's sign-in redirects (devSignIn below)
  const created = initializeAuth(app, { persistence: [indexedDBLocalPersistence, browserLocalPersistence] });
  if (isEmulator && runtime.authEmulator) {
    connectAuthEmulator(created, runtime.authEmulator, { disableWarnings: true });
    window.__aljE2E = {
      async signInWithIdToken(idToken: string) {
        await signInWithCredential(created, GoogleAuthProvider.credential(idToken));
      },
    };
  }
  auth = created;
  return created;
}

/** Production sign-in: the Google access token received on /competitions (implicit OAuth, lib/oauth.ts). */
export async function signInWithGoogleAccessToken(accessToken: string): Promise<void> {
  await signInWithCredential(firebaseAuth(), GoogleAuthProvider.credential(null, accessToken));
}

/** Dev: the Auth emulator's account picker (a redirect: sign-in can start without a click, ?login=1). */
export async function devSignIn(): Promise<void> {
  await signInWithRedirect(firebaseAuth(), new GoogleAuthProvider(), browserPopupRedirectResolver);
}

/** Dev: back from the emulator's account picker, true when a sign-in just completed. */
export async function completeDevSignIn(): Promise<boolean> {
  const result = await getRedirectResult(firebaseAuth(), browserPopupRedirectResolver);
  return !!result?.user;
}
