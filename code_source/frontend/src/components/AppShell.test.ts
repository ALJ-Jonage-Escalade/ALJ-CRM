import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { AUTH_KEY, type Auth, type AuthState } from "../composables/auth";
import type { PageId } from "../lib/access";
import { API_KEY, type ApiFetch } from "../lib/api";
import { STORE_KEY, type OfflineStore } from "../lib/store";
import { SIGN_IN_ERROR_KEY } from "../composables/signIn";
import AppShell from "./AppShell.vue";
import { dialogs } from "../composables/dialogs";

const USER = { uid: "u1", email: "albus@alj-escalade.fr" };

function render(
  state: AuthState,
  googleStatus = "ok",
  page: PageId = "accueil",
  offlineRead = false,
  queued = 0,
  signInError: string | null = null,
) {
  const auth: Auth = { state: ref(state), login: vi.fn(), logout: vi.fn(async () => {}), retry: vi.fn(async () => {}), stop: vi.fn() };
  const api: ApiFetch = vi.fn(async () => new Response(JSON.stringify({ status: googleStatus })));
  const wrapper = mount(AppShell, {
    props: { page, title: "Titre", offlineRead },
    slots: { default: '<p id="page-body">contenu</p>' },
    global: {
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [STORE_KEY]: storeWith(queued), [SIGN_IN_ERROR_KEY]: ref(signInError) },
      stubs: { VersionBadge: true },
    },
  });
  return { wrapper, auth, api };
}

/** A store holding `n` changes made offline for the user. */
function storeWith(n: number): OfflineStore {
  const queued = vi.fn(async (uid: string | null) => (uid === USER.uid ? Array.from({ length: n }, (_, i) => ({ key: String(i) })) : []));
  return { queued } as unknown as OfflineStore;
}

describe("AppShell", () => {
  it("asks before a logout that would lose changes made offline", async () => {
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValue(false);
    const { wrapper, auth } = render({ status: "signedIn", user: USER, role: "coach" }, "ok", "accueil", false, 2);
    await wrapper.find("#logout-btn").trigger("click");
    await flushPromises();
    expect(confirm).toHaveBeenCalledWith(
      expect.objectContaining({ message: "2 modifications faites hors ligne pas encore envoyées seront perdues. Se déconnecter ?" }),
    );
    expect(auth.logout).not.toHaveBeenCalled();
    confirm.mockResolvedValue(true);
    await wrapper.find("#logout-btn").trigger("click");
    await flushPromises();
    expect(auth.logout).toHaveBeenCalledOnce();
    confirm.mockRestore();
  });

  it("signs out at once with nothing waiting", async () => {
    const confirm = vi.spyOn(dialogs, "confirm");
    const { wrapper, auth } = render({ status: "signedIn", user: USER, role: "coach" });
    await wrapper.find("#logout-btn").trigger("click");
    await flushPromises();
    expect(confirm).not.toHaveBeenCalled();
    expect(auth.logout).toHaveBeenCalledOnce();
  });

  it("shows only a full-screen splash while the session loads", () => {
    const { wrapper } = render({ status: "loading" });
    expect(wrapper.find("#session-check").text()).toBe("Vérification de la connexion…");
    expect(wrapper.find("nav").exists()).toBe(false);
    expect(wrapper.find("#gate").exists()).toBe(false);
    expect(wrapper.find("#content").exists()).toBe(false);
  });

  it("asks a signed-out visitor to sign in, full screen", async () => {
    const { wrapper, auth } = render({ status: "signedOut" });
    expect(wrapper.find("#login-screen").exists()).toBe(true);
    expect(wrapper.find("nav").exists()).toBe(false);
    expect(wrapper.find("header").exists()).toBe(false);
    expect(wrapper.find("#who").exists()).toBe(false);
    expect(wrapper.find("#logout-btn").exists()).toBe(false);
    expect(wrapper.find("#content").exists()).toBe(false);
    expect(wrapper.find('[data-testid="sign-in-error"]').exists()).toBe(false);
    await wrapper.find("#gate-login").trigger("click");
    expect(auth.login).toHaveBeenCalledOnce();
  });

  it("explains a failed Google sign-in on the gate", () => {
    const { wrapper } = render({ status: "signedOut" }, "ok", "competitions", true, 0, "Connexion Google annulée.");
    expect(wrapper.find('[data-testid="sign-in-error"]').text()).toContain("Connexion Google annulée.");
  });

  it.each(["admin", "coach"] as const)("renders the page for %s", async (role) => {
    const { wrapper } = render({ status: "signedIn", user: USER, role });
    expect(wrapper.find("#page-body").exists()).toBe(true);
    expect(wrapper.find("#gate").exists()).toBe(false);
    expect(wrapper.find("#who").text()).toContain(USER.email);
    await flushPromises();
    expect(wrapper.find("#google-auth-warning").isVisible()).toBe(false);
  });

  it.each(["readonly", null] as const)("refuses the office to %s, full screen", async (role) => {
    const { wrapper, auth, api } = render({ status: "signedIn", user: USER, role });
    expect(wrapper.find("#gate").text()).toContain("Accès réservé");
    expect(wrapper.find('[data-testid="gate-account"]').text()).toBe(USER.email);
    // Read-only accounts may still open the competitions: the gate links to them
    expect(wrapper.findAll('[data-testid="gate-pages"] a').map((link) => link.attributes("data-page"))).toEqual(
      role === "readonly" ? ["competitions"] : [],
    );
    expect(wrapper.find("nav").exists()).toBe(false);
    expect(wrapper.find("#content").exists()).toBe(false);
    await wrapper.find("#gate-logout").trigger("click");
    await flushPromises();
    expect(auth.logout).toHaveBeenCalledOnce();
    expect(api).not.toHaveBeenCalled(); // no club data asked for a non-staff account
  });

  it("keeps the menu offline, towards the pages readable offline", async () => {
    const { wrapper, auth } = render({ status: "error", user: USER, message: "Serveur injoignable", offline: true });
    expect(wrapper.find("#gate").text()).toContain("Serveur injoignable");
    expect(wrapper.find('[data-testid="offline-pages"]').exists()).toBe(true);
    expect(wrapper.findAll("nav a")).toHaveLength(8);
    expect(wrapper.find("#content").exists()).toBe(false);
    expect(wrapper.find("#logout-btn").exists()).toBe(true);
    await wrapper.find("#gate-retry").trigger("click");
    expect(auth.retry).toHaveBeenCalledOnce();
  });

  it("offers a retry and a logout, full screen, when the server refused the role", async () => {
    const { wrapper, auth } = render({ status: "error", user: USER, message: "Session refusée par le serveur", offline: false });
    expect(wrapper.find("#gate").text()).toContain("Session refusée par le serveur");
    expect(wrapper.find("nav").exists()).toBe(false);
    expect(wrapper.find('[data-testid="offline-pages"]').exists()).toBe(false);
    await wrapper.find("#gate-retry").trigger("click");
    expect(auth.retry).toHaveBeenCalledOnce();
    await wrapper.find("#gate-logout").trigger("click");
    await flushPromises();
    expect(auth.logout).toHaveBeenCalledOnce();
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
    const { wrapper } = render({ status: "error", user: USER, message: "Serveur injoignable", offline: true });
    expect(wrapper.find('nav a[data-page="accueil"]').attributes("aria-current")).toBe("page");
    expect(wrapper.find('nav a[data-page="adherents"]').attributes("aria-current")).toBeUndefined();
    expect(wrapper.findAll("nav a")).toHaveLength(8);
  });

  it("lists Adhérents on a computer and the directory on a phone", () => {
    const { wrapper } = render({ status: "signedIn", user: USER, role: "coach" });
    expect(wrapper.find('nav a[data-page="adherents"]').classes()).toEqual(expect.arrayContaining(["hidden", "md:flex"]));
    expect(wrapper.find('nav a[data-page="annuaire"]').classes()).toEqual(expect.arrayContaining(["flex", "md:hidden"]));
    expect(wrapper.find('nav a[data-page="planning"]').classes()).not.toContain("hidden");
  });

  it.each([
    ["admin", 8],
    ["coach", 6],
    ["readonly", 1],
    [null, 0],
  ] as const)("lists the pages %s may open", (role, count) => {
    // On Compétitions, the page every role but none may open (elsewhere a read-only account gets the full-screen gate)
    const { wrapper } = render({ status: "signedIn", user: USER, role }, "ok", "competitions", true);
    expect(wrapper.findAll("nav a")).toHaveLength(count);
  });

  it("hides the admin pages from a coach", () => {
    const { wrapper } = render({ status: "signedIn", user: USER, role: "coach" });
    expect(wrapper.find('nav a[data-page="parametres"]').exists()).toBe(false);
    expect(wrapper.find('nav a[data-page="communications"]').exists()).toBe(false);
  });

  it("keeps an admin page from a coach", async () => {
    const { wrapper, api } = render({ status: "signedIn", user: USER, role: "coach" }, "ok", "parametres");
    expect(wrapper.find("#gate").text()).toContain("Réservé aux administrateurs");
    expect(wrapper.find("#content").exists()).toBe(false);
    await flushPromises();
    expect(api).toHaveBeenCalledOnce(); // the shell's Google token check only, nothing for the page
  });

  it("renders an admin page for an admin", () => {
    const { wrapper } = render({ status: "signedIn", user: USER, role: "admin" }, "ok", "parametres");
    expect(wrapper.find("#page-body").exists()).toBe(true);
    expect(wrapper.find("#gate").exists()).toBe(false);
  });
});
