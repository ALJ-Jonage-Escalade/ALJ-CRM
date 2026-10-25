/// <reference types="vite/client" />

/** code_source/VERSION, injected by vite.config.ts. */
declare const __APP_VERSION__: string;

/** /runtime-config.js (api/web/pwa.py): Firebase emulator in dev, nothing else in production. */
interface AljRuntime {
  env: "prod" | "dev";
  projectId?: string;
  authEmulator?: string;
}

interface Window {
  ALJ_RUNTIME?: AljRuntime;
  /** Set by the classic script of index.html when the browser is older than the build target. */
  ALJ_UNSUPPORTED?: boolean;
  /** Emulator only: lets the e2e tests sign in without the account picker (e2e/helpers/auth.py). */
  __aljE2E?: { signInWithIdToken(idToken: string): Promise<void> };
}
