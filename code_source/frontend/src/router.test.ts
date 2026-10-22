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

/** One route per access level: the app has no admin route yet (Paramètres comes next). */
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
  ["role not checked", { status: "error", user: USER, message: "x" }],
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

  it("sends a coach back once the role is known", async () => {
    const { state, at } = await setup({ status: "loading" }, "/bureau/parametres");
    state.value = signedIn("coach");
    await flushPromises();
    expect(at()).toBe("/bureau/?reserve=/bureau/parametres");
  });

  it("keeps an admin on the admin page when the role is known", async () => {
    const { state, at } = await setup({ status: "loading" }, "/bureau/parametres");
    state.value = signedIn("admin");
    await flushPromises();
    expect(at()).toBe("/bureau/parametres");
  });

  it("sends the page back when a coach signs in over an admin session", async () => {
    const { state, at } = await setup(signedIn("admin"), "/bureau/parametres");
    state.value = signedIn("coach");
    await flushPromises();
    expect(at()).toBe("/bureau/?reserve=/bureau/parametres");
  });
});

describe("app routes", () => {
  it("declare their access", () => {
    for (const route of routes) expect(["public", "staff", "admin"]).toContain(route.meta?.access);
  });

  it("show unknown paths to anyone", async () => {
    const router = createAppRouter(fakeAuth(signedIn("coach")).auth, createMemoryHistory());
    await router.push("/bureau/inconnu");
    expect(router.currentRoute.value.meta.access).toBe("public");
  });
});
