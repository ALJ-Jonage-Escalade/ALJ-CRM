import { createApp } from "vue";
import App from "./App.vue";
import { AUTH_KEY, sharedAuth } from "./composables/auth";
import { API_KEY, apiFetch } from "./lib/api";
import { registerServiceWorker } from "./lib/version";
import { createAppRouter } from "./router";
import "./styles.css";

// Older browsers: index.html shows its message instead
if (!window.ALJ_UNSUPPORTED) {
  const auth = sharedAuth();
  createApp(App)
    .use(createAppRouter(auth))
    .provide(AUTH_KEY, auth)
    .provide(API_KEY, apiFetch)
    .mount("#app");
  registerServiceWorker();
}
