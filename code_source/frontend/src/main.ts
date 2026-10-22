import { createApp } from "vue";
import App from "./App.vue";
import { AUTH_KEY, sharedAuth } from "./composables/auth";
import { API_KEY, apiFetch } from "./lib/api";
import { registerServiceWorker } from "./lib/version";
import { router } from "./router";
import "./styles.css";

// Older browsers: index.html shows its message instead
if (!window.ALJ_UNSUPPORTED) {
  createApp(App)
    .use(router)
    .provide(AUTH_KEY, sharedAuth())
    .provide(API_KEY, apiFetch)
    .mount("#app");
  registerServiceWorker();
}
