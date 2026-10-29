/* Routes migrated to the Vue app. FastAPI serves the app's entry page for these paths only
   (api/web/pages.py); links to the other pages are plain <a href> (full page load).
   Every route declares meta.access (lib/access.ts); the guards send a coach who opens an admin page back to
   Accueil. Signed-out, unverified and non-staff visitors stay on the page, which shows the sign-in gate.
   Sub-pages (lib/access.ts subPages) are child routes: they carry their page's access (the guards check the page);
   AppShell checks the sub-page itself and sends back to the page's index route. */
import { watch } from "vue";
import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalized,
  type RouteLocationRaw,
  type Router,
  type RouteComponent,
  type RouteRecordRaw,
  type RouterHistory,
} from "vue-router";
import type { Auth } from "./composables/auth";
import { HOME, pageAccess, REFUSED_QUERY, subPages, verdict, type Access, type PageId } from "./lib/access";
import AccueilPage from "./pages/AccueilPage.vue";
// The pages readable offline are in the main bundle (the service worker precaches every chunk, but the main bundle
// does not depend on it)
import CompetitionsPage from "./pages/CompetitionsPage.vue";
import CompetitionsBalancePage from "./pages/competitions/CompetitionsBalancePage.vue";
import CompetitionsCoachesPage from "./pages/competitions/CompetitionsCoachesPage.vue";
import CompetitionsListPage from "./pages/competitions/CompetitionsListPage.vue";
import DirectoryPage from "./pages/DirectoryPage.vue";
import NotFoundPage from "./pages/NotFoundPage.vue";

// Loaded when opened: Accueil (the most opened page) does not wait for them
const AdherentsPage = () => import("./pages/AdherentsPage.vue");
const CommunicationsPage = () => import("./pages/CommunicationsPage.vue");
const OutilsPage = () => import("./pages/OutilsPage.vue");
const ParametresPage = () => import("./pages/ParametresPage.vue");
const PlanningPage = () => import("./pages/PlanningPage.vue");
const CompetitionsHelloAssoPage = () => import("./pages/competitions/CompetitionsHelloAssoPage.vue"); // online only
const OutilsMapPage = () => import("./pages/outils/OutilsMapPage.vue");
const OutilsPivotPage = () => import("./pages/outils/OutilsPivotPage.vue"); // with the pivot table library
const OutilsStatsPage = () => import("./pages/outils/OutilsStatsPage.vue");
const OutilsPresencePage = () => import("./pages/outils/OutilsPresencePage.vue");
const OutilsFfmePage = () => import("./pages/outils/OutilsFfmePage.vue");
const OutilsFfmeImportPage = () => import("./pages/outils/OutilsFfmeImportPage.vue");

/** Component of each sub-page, by page then sub-page id (lib/access.ts subPages). */
const SUB_COMPONENTS: Partial<Record<PageId, Record<string, RouteComponent>>> = {
  competitions: {
    competitions: CompetitionsListPage,
    helloasso: CompetitionsHelloAssoPage,
    bilan: CompetitionsBalancePage,
    coachs: CompetitionsCoachesPage,
  },
  outils: {
    map: OutilsMapPage,
    pivot: OutilsPivotPage,
    stats: OutilsStatsPage,
    presence: OutilsPresencePage,
    ffme: OutilsFfmePage,
    "ffme-import": OutilsFfmeImportPage,
  },
};

declare module "vue-router" {
  interface RouteMeta {
    access: Access;
    /** Id of the sub-page a child route opens. */
    sub?: string;
    /** The page layout keeps its sub-pages mounted while switching (loaded data and typed values kept). */
    keepAlive?: boolean;
  }
}

/** The child routes of a page's sub-pages, named `<name>` for the index route and `<name>-<sub-page id>` for the others. */
function subRoutes(id: PageId, name: string, keepAlive = false): RouteRecordRaw[] {
  return subPages(id).map((sub) => ({
    path: sub.path,
    name: sub.path ? `${name}-${sub.id}` : name,
    component: SUB_COMPONENTS[id]![sub.id]!,
    meta: { access: pageAccess(id), sub: sub.id, ...(keepAlive && { keepAlive }) },
  }));
}

export const routes: RouteRecordRaw[] = [
  // The server redirects / to the competitions (api/web/pages.py); same offline, where the service worker answers
  { path: "/", redirect: "/competitions", meta: { access: "public" } },
  { path: HOME, name: "accueil", component: AccueilPage, meta: { access: pageAccess("accueil") } },
  { path: "/bureau/adherents", name: "adherents", component: AdherentsPage, meta: { access: pageAccess("adherents") } },
  // Same screen on both addresses: /competitions is the PWA's start page and the Google sign-in callback (main.ts)
  {
    path: "/competitions",
    component: CompetitionsPage,
    meta: { access: pageAccess("competitions") },
    children: subRoutes("competitions", "competitions-pwa"),
  },
  {
    path: "/bureau/competitions",
    component: CompetitionsPage,
    meta: { access: pageAccess("competitions") },
    children: subRoutes("competitions", "competitions"),
  },
  { path: "/index", name: "annuaire", component: DirectoryPage, meta: { access: pageAccess("annuaire") } },
  { path: "/bureau/communications", name: "communications", component: CommunicationsPage, meta: { access: pageAccess("communications") } },
  { path: "/bureau/planning", name: "planning", component: PlanningPage, meta: { access: pageAccess("planning") } },
  {
    path: "/bureau/outils",
    component: OutilsPage,
    meta: { access: pageAccess("outils") },
    children: subRoutes("outils", "outils", true),
  },
  { path: "/bureau/parametres", name: "parametres", component: ParametresPage, meta: { access: pageAccess("parametres") } },
  { path: "/:unknown(.*)*", component: NotFoundPage, meta: { access: "public" } },
];

/** Former tab of a page with sub-pages (?section=bilan, ?tab=ffme): the sub-page's address, the rest of the query kept. */
const FORMER_TAB_QUERIES = ["section", "tab"];

function formerTabRedirect(to: RouteLocationNormalized): RouteLocationRaw | null {
  const index = to.matched.find((record) => record.children.length);
  for (const key of FORMER_TAB_QUERIES) {
    const requested = to.query[key];
    const child = index?.children.find((record) => record.path && record.path === requested);
    if (index && child) {
      const query = { ...to.query };
      delete query[key];
      return { path: `${index.path}/${child.path}`, query };
    }
  }
  return null;
}

function redirectFor(to: RouteLocationNormalized, auth: Auth): RouteLocationRaw | true {
  const former = formerTabRedirect(to);
  if (former) {
    return former;
  }
  if (verdict(auth.state.value, to.meta.access ?? "public") !== "adminOnly") {
    return true;
  }
  return { path: HOME, query: { [REFUSED_QUERY]: to.path } };
}

/** Checks every navigation, and the current page again whenever the session changes (role answered, other account). */
export function installGuards(router: Router, auth: Auth): void {
  router.beforeEach((to) => redirectFor(to, auth));
  watch(auth.state, () => {
    const target = redirectFor(router.currentRoute.value, auth);
    if (target !== true) {
      void router.replace(target);
    }
  });
}

export function createAppRouter(auth: Auth, history: RouterHistory = createWebHistory()): Router {
  const router = createRouter({ history, routes });
  installGuards(router, auth);
  return router;
}
