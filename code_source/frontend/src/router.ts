/* Routes migrated to the Vue app. FastAPI serves the app's entry page for these paths only
   (api/web/pages.py); links to the other pages are plain <a href> (full page load). */
import { createRouter, createWebHistory } from "vue-router";
import AccueilPage from "./pages/AccueilPage.vue";
import NotFoundPage from "./pages/NotFoundPage.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/bureau/", component: AccueilPage },
    { path: "/:unknown(.*)*", component: NotFoundPage },
  ],
});
