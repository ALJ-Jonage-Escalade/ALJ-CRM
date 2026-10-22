import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { AUTH_KEY, type Auth, type AuthState } from "../composables/auth";
import type { PageId } from "../lib/access";
import { API_KEY, type ApiFetch } from "../lib/api";
import AppShell from "./AppShell.vue";

const USER = { uid: "u1", email: "albus@alj-escalade.fr" };

function render(state: AuthState, googleStatus = "ok", page: PageId = "accueil", offlineRead = false) {
  const auth: Auth = { state: ref(state), login: vi.fn(), logout: vi.fn(async () => {}), retry: vi.fn(async () => {}), stop: vi.fn() };
  const api: ApiFetch = vi.fn(async () => new Response(JSON.stringify({ status: googleStatus })));
  const wrapper = mount(AppShell, {
    props: { page, title: "Titre", offlineRead },
    slots: { default: '<p id="page-body">contenu</p>' },
    global: { provide: { [AUTH_KEY]: auth, [API_KEY]: api }, stubs: { VersionBadge: true } },
  });
  return { wrapper, auth, api };
}

describe("AppShell", () => {
  it("shows neither the gate nor the content while the session loads", () => {
    const { wrapper } = render({ status: "loading" });
    expect(wrapper.find("#who").text()).toBe("Vérification de la connexion…");
    expect(wrapper.find("#gate").exists()).toBe(false);
    expect(wrapper.find("#content").exists()).toBe(false);
  });

  it("asks a signed-out visitor to sign in", async () => {
    const { wrapper, auth } = render({ status: "signedOut" });
    expect(wrapper.find("#who").text()).toBe("Non connecté");
    expect(wrapper.find("#logout-btn").exists()).toBe(false);
    expect(wrapper.find("#content").exists()).toBe(false);
    await wrapper.find("#gate-login").trigger("click");
    expect(auth.login).toHaveBeenCalledOnce();
  });

  it.each(["admin", "coach"] as const)("renders the page for %s", async (role) => {
    const { wrapper } = render({ status: "signedIn", user: USER, role });
    expect(wrapper.find("#page-body").exists()).toBe(true);
    expect(wrapper.find("#gate").exists()).toBe(false);
    expect(wrapper.find("#who").text()).toContain(USER.email);
    await flushPromises();
    expect(wrapper.find("#google-auth-warning").isVisible()).toBe(false);
  });

  it.each(["readonly", null] as const)("refuses the office to %s", async (role) => {
    const { wrapper, auth, api } = render({ status: "signedIn", user: USER, role });
    expect(wrapper.find("#gate").text()).toContain("Accès réservé");
    expect(wrapper.find("#content").exists()).toBe(false);
    await wrapper.find("#gate-logout").trigger("click");
    expect(auth.logout).toHaveBeenCalledOnce();
    expect(api).not.toHaveBeenCalled();  // no club data asked for a non-staff account
  });

  it("offers a retry when the role could not be checked", async () => {
    const { wrapper, auth } = render({ status: "error", user: USER, message: "Serveur injoignable", offline: true });
    expect(wrapper.find("#gate").text()).toContain("Serveur injoignable");
    expect(wrapper.find("#content").exists()).toBe(false);
    expect(wrapper.find("#logout-btn").exists()).toBe(true);
    await wrapper.find("#gate-retry").trigger("click");
    expect(auth.retry).toHaveBeenCalledOnce();
  });

  it("shows a page readable offline when only the network is missing", async () => {
    const offline: AuthState = { status: "error", user: USER, message: "Serveur injoignable", offline: true };
    const { wrapper, api } = render(offline, "ok", "annuaire", true);
    expect(wrapper.find("#page-body").exists()).toBe(true);
    expect(wrapper.find("#offline-notice").exists()).toBe(true);
    expect(wrapper.find("#gate").exists()).toBe(false);
    await flushPromises();
    expect(api).not.toHaveBeenCalled();

    const refused = render({ ...offline, offline: false }, "ok", "annuaire", true);
    expect(refused.wrapper.find("#gate").exists()).toBe(true);
    expect(refused.wrapper.find("#page-body").exists()).toBe(false);
  });

  it("warns staff when the club's Google token has expired", async () => {
    const { wrapper, api } = render({ status: "signedIn", user: USER, role: "admin" }, "expired");
    await flushPromises();
    expect(api).toHaveBeenCalledWith("/api/auth/google/status");
    expect(wrapper.find("#google-auth-warning").isVisible()).toBe(true);
  });

  it("marks the current page in the navigation", () => {
    const { wrapper } = render({ status: "signedOut" });
    expect(wrapper.find('nav a[data-page="accueil"]').attributes("aria-current")).toBe("page");
    expect(wrapper.find('nav a[data-page="adherents"]').attributes("aria-current")).toBeUndefined();
    expect(wrapper.findAll("nav a")).toHaveLength(8);
  });

  it.each([
    ["admin", 8],
    ["coach", 6],
    ["readonly", 1],
    [null, 0],
  ] as const)("lists the pages %s may open", (role, count) => {
    const { wrapper } = render({ status: "signedIn", user: USER, role });
    expect(wrapper.findAll("nav a")).toHaveLength(count);
    if (role === "coach") {
      expect(wrapper.find('nav a[data-page="parametres"]').exists()).toBe(false);
      expect(wrapper.find('nav a[data-page="communications"]').exists()).toBe(false);
    }
  });

  it("keeps an admin page from a coach", async () => {
    const { wrapper, api } = render({ status: "signedIn", user: USER, role: "coach" }, "ok", "parametres");
    expect(wrapper.find("#gate").text()).toContain("Réservé aux administrateurs");
    expect(wrapper.find("#content").exists()).toBe(false);
    await flushPromises();
    expect(api).toHaveBeenCalledOnce();  // the shell's Google token check only, nothing for the page
  });

  it("renders an admin page for an admin", () => {
    const { wrapper } = render({ status: "signedIn", user: USER, role: "admin" }, "ok", "parametres");
    expect(wrapper.find("#page-body").exists()).toBe(true);
    expect(wrapper.find("#gate").exists()).toBe(false);
  });
});
