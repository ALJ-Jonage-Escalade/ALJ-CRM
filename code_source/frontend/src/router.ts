/* Routes migrated to the Vue app. FastAPI serves the app's entry page for these paths only
   (api/web/pages.py); links to the other pages are plain <a href> (full page load).
   Every route declares meta.access (lib/access.ts); the guards send a coach who opens an admin page back to
   Accueil. Signed-out, unverified and non-staff visitors stay on the page, which shows the sign-in gate. */
import { watch } from "vue";
import { createRouter, createWebHistory, type RouteLocationNormalized, type RouteLocationRaw, type Router, type RouteRecordRaw, type RouterHistory } from "vue-router";
import type { Auth } from "./composables/auth";
import { HOME, pageAccess, REFUSED_QUERY, verdict, type Access } from "./lib/access";
import AccueilPage from "./pages/AccueilPage.vue";
import NotFoundPage from "./pages/NotFoundPage.vue";

// Loaded when opened: Accueil (the most opened page) does not wait for them
const CommunicationsPage = () => import("./pages/CommunicationsPage.vue");
const OutilsPage = () => import("./pages/OutilsPage.vue");
const ParametresPage = () => import("./pages/ParametresPage.vue");
const PlanningPage = () => import("./pages/PlanningPage.vue");

declare module "vue-router" {
  interface RouteMeta {
    access: Access;
  }
}

export const routes: RouteRecordRaw[] = [
  { path: HOME, name: "accueil", component: AccueilPage, meta: { access: pageAccess("accueil") } },
  { path: "/bureau/communications", name: "communications", component: CommunicationsPage, meta: { access: pageAccess("communications") } },
  { path: "/bureau/planning", name: "planning", component: PlanningPage, meta: { access: pageAccess("planning") } },
  { path: "/bureau/outils", name: "outils", component: OutilsPage, meta: { access: pageAccess("outils") } },
  { path: "/bureau/parametres", name: "parametres", component: ParametresPage, meta: { access: pageAccess("parametres") } },
  { path: "/:unknown(.*)*", component: NotFoundPage, meta: { access: "public" } },
];

function redirectFor(to: RouteLocationNormalized, auth: Auth): RouteLocationRaw | true {
  if (verdict(auth.state.value, to.meta.access ?? "public") !== "adminOnly") return true;
  return { path: HOME, query: { [REFUSED_QUERY]: to.path } };
}

/** Checks every navigation, and the current page again whenever the session changes (role answered, other account). */
export function installGuards(router: Router, auth: Auth): void {
  router.beforeEach((to) => redirectFor(to, auth));
  watch(auth.state, () => {
    const target = redirectFor(router.currentRoute.value, auth);
    if (target !== true) void router.replace(target);
  });
}

export function createAppRouter(auth: Auth, history: RouterHistory = createWebHistory()): Router {
  const router = createRouter({ history, routes });
  installGuards(router, auth);
  return router;
}
