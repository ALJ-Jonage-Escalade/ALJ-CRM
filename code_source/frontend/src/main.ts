import { createApp, ref } from "vue";
import App from "./App.vue";
import { AUTH_KEY, sharedAuth } from "./composables/auth";
import { bindOfflineStore } from "./composables/offlineSession";
import { handleSignIn, SIGN_IN_ERROR_KEY } from "./composables/signIn";
import { API_KEY, apiFetch } from "./lib/api";
import { CLIENT_KEY, createApiClient } from "./lib/client";
import { completeDevSignIn, devSignIn, signInWithGoogleAccessToken } from "./lib/firebase";
import { isEmulator } from "./lib/runtime";
import { offlineStore, STORE_KEY } from "./lib/store";
import { registerServiceWorker } from "./lib/version";
import { createAppRouter } from "./router";
import "./styles.css";

// Older browsers: index.html shows its message instead
if (!window.ALJ_UNSUPPORTED) {
  const auth = sharedAuth();
  const store = offlineStore();
  bindOfflineStore(auth.state, store);
  // Google sign-in, on /competitions: run before the router reads the address (the token leaves it at once)
  const signInError = ref<string | null>(null);
  void handleSignIn({
    url: location,
    storage: sessionStorage,
    replaceUrl: (url) => history.replaceState(history.state, "", url),
    navigate: (url) => location.assign(url),
    emulator: isEmulator,
    signInWithToken: signInWithGoogleAccessToken,
    devSignIn,
    completeDevSignIn,
  }).then((message) => (signInError.value = message));
  createApp(App)
    .provide(SIGN_IN_ERROR_KEY, signInError)
    .use(createAppRouter(auth))
    .provide(AUTH_KEY, auth)
    .provide(STORE_KEY, store)
    .provide(API_KEY, apiFetch)
    .provide(CLIENT_KEY, createApiClient(apiFetch))
    .mount("#app");
  registerServiceWorker();
}
