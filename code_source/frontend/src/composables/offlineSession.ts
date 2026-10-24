/* The offline copy (lib/store.ts) follows the session, on every page of the app: wiped when signed out (logout, from
   any page), and when another account signs in on this device (store.start wipes the former owner's data). */
import { watch, type Ref } from "vue";
import type { OfflineStore } from "../lib/store";
import type { AuthState } from "./auth";

export function bindOfflineStore(state: Readonly<Ref<AuthState>>, store: OfflineStore): () => void {
  return watch(
    // "": signed out; null: not known yet
    () => (state.value.status === "signedOut" ? "" : state.value.status === "loading" ? null : state.value.user.uid),
    (uid) => {
      if (uid === "") {
        void store.clearAll();
      } else if (uid) {
        void store.start(uid);
      }
    },
    { immediate: true },
  );
}
