import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { defineComponent, ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import type { Auth, AuthState } from "./composables/auth";
import type { Access } from "./lib/access";
import type { Role } from "./lib/roles";
import { createAppRouter, installGuards, routes } from "./router";

const USER = { uid: "u1", email: "u@example.org" };
const signedIn = (role: Role): AuthState => ({ status: "signedIn", user: USER, role });
const Empty = defineComponent({ render: () => null });

function fakeAuth(initial: AuthState) {
  const state = ref<AuthState>(initial);
  const auth: Auth = { state, login: vi.fn(), logout: vi.fn(async () => {}), retry: vi.fn(async () => {}), stop: vi.fn() };
  return { auth, state };
}

/** One route per access level. */
async function setup(initial: AuthState, path: string) {
  const { auth, state } = fakeAuth(initial);
  const page = (p: string, access: Access) => ({ path: p, component: Empty, meta: { access } });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [page("/bureau/", "staff"), page("/bureau/parametres", "admin"), page("/competitions", "public")],
  });
  installGuards(router, auth);
  await router.push(path);
  return { router, state, at: () => router.currentRoute.value.fullPath };
}

const SESSIONS: [string, AuthState][] = [
  ["loading", { status: "loading" }],
  ["signed out", { status: "signedOut" }],
  ["role not checked", { status: "error", user: USER, message: "x", offline: false }],
  ["admin", signedIn("admin")],
  ["coach", signedIn("coach")],
  ["readonly", signedIn("readonly")],
  ["no role", signedIn(null)],
];

describe("router guards", () => {
  it.each(SESSIONS)("%s: the callback route and Accueil open", async (_name, session) => {
    expect((await setup(session, "/competitions?login=1")).at()).toBe("/competitions?login=1");
    // Accueil shows the sign-in / access gate itself: no redirect
    expect((await setup(session, "/bureau/")).at()).toBe("/bureau/");
  });

  it.each(SESSIONS.filter(([name]) => name !== "coach"))("%s: an admin page opens (the page shows its gate)", async (_name, session) => {
    expect((await setup(session, "/bureau/parametres")).at()).toBe("/bureau/parametres");
  });

  it("sends a coach back to Accueil from an admin page", async () => {
    const { at } = await setup(signedIn("coach"), "/bureau/parametres");
    expect(at()).toBe("/bureau/?reserve=/bureau/parametres");
  });

  it.each<[string, AuthState, AuthState, string]>([
    ["a coach once the role is known", { status: "loading" }, signedIn("coach"), "/bureau/?reserve=/bureau/parametres"],
    ["an admin once the role is known", { status: "loading" }, signedIn("admin"), "/bureau/parametres"],
    ["a coach signing in over an admin session", signedIn("admin"), signedIn("coach"), "/bureau/?reserve=/bureau/parametres"],
  ])("follows the session on an admin page: %s", async (_case, initial, next, expected) => {
    const { state, at } = await setup(initial, "/bureau/parametres");
    state.value = next;
    await flushPromises();
    expect(at()).toBe(expected);
  });
});

describe("app routes", () => {
  it("declare their access", () => {
    for (const route of routes) {
      expect(["public", "viewer", "staff", "admin"]).toContain(route.meta?.access);
    }
  });

  it.each(["/bureau/communications", "/bureau/parametres"])("send a coach back from %s", async (path) => {
    const router = createAppRouter(fakeAuth(signedIn("coach")).auth, createMemoryHistory());
    await router.push(path);
    expect(router.currentRoute.value.fullPath).toBe(`/bureau/?reserve=${path}`);
  });

  it.each(["/bureau/adherents", "/bureau/planning", "/bureau/outils?tab=ffme", "/index", "/index?vue=pwa"])(
    "open %s to a coach",
    async (path) => {
      const router = createAppRouter(fakeAuth(signedIn("coach")).auth, createMemoryHistory());
      await router.push(path);
      expect(router.currentRoute.value.fullPath).toBe(path);
    },
  );

  it("open the member record links of the former page in Adhérents itself", async () => {
    const router = createAppRouter(fakeAuth(signedIn("coach")).auth, createMemoryHistory());
    await router.push("/bureau/adherents?id=12&saison=2026-2027");
    expect(router.currentRoute.value.name).toBe("adherents");
    expect(router.currentRoute.value.query).toEqual({ id: "12", saison: "2026-2027" });
  });

  it("open the directory on /index, offline too (the page shows its copy)", async () => {
    const offline: AuthState = { status: "error", user: USER, message: "x", offline: true };
    const router = createAppRouter(fakeAuth(offline).auth, createMemoryHistory());
    await router.push("/index");
    expect([router.currentRoute.value.name, router.currentRoute.value.meta.access]).toEqual(["annuaire", "staff"]);
  });

  it.each(["/competitions", "/competitions?vue=mobile", "/bureau/competitions?id=3"])("open %s to a read-only account", async (path) => {
    const router = createAppRouter(fakeAuth(signedIn("readonly")).auth, createMemoryHistory());
    await router.push(path);
    expect(router.currentRoute.value.fullPath).toBe(path);
    expect(router.currentRoute.value.meta.access).toBe("viewer");
  });

  // Former addresses the server answers with the entry page (/ too, where the service worker answers it offline)
  it.each([
    ["/", "competitions-pwa"],
    ["/competitions?vue=mobile", "competitions-pwa"],
    ["/competitions?vue=pwa", "competitions-pwa"],
    ["/index?vue=pwa", "annuaire"],
    ["/bureau/?vue=bureau", "accueil"],
    ["/bureau/competitions?id=3", "competitions"],
  ])("open the former address %s on its screen", async (path, name) => {
    const router = createAppRouter(fakeAuth(signedIn("admin")).auth, createMemoryHistory());
    await router.push(path);
    expect(router.currentRoute.value.name).toBe(name);
  });

  it("show unknown paths to anyone", async () => {
    const router = createAppRouter(fakeAuth(signedIn("coach")).auth, createMemoryHistory());
    await router.push("/bureau/inconnu");
    expect(router.currentRoute.value.meta.access).toBe("public");
  });
});
