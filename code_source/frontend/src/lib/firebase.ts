/* Firebase only signs the user in: its ID token is sent to the API, which decides the rights.
   Same project and app name as web/shared/alj-firebase.js, so the session (IndexedDB) is shared
   with the pages not migrated yet: no second sign-in when moving between them. */
import { initializeApp } from "@firebase/app";
import {
  browserLocalPersistence, connectAuthEmulator, GoogleAuthProvider, indexedDBLocalPersistence,
  initializeAuth, signInWithCredential, type Auth,
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
  // No popup/redirect resolver: sign-in goes through the competitions page (composables/auth.ts)
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
