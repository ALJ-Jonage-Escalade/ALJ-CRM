import { beforeEach, describe, expect, it, vi } from "vitest";
import { authorizeUrl, readFragment } from "../lib/oauth";
import { AFTER_LOGIN_KEY } from "./auth";
import { handleSignIn, type SignInDeps } from "./signIn";

function setup(address: string, options: { emulator?: boolean; devResult?: boolean } = {}) {
  const u = new URL(address, "https://alj.example");
  const deps = {
    url: { origin: u.origin, pathname: u.pathname, search: u.search, hash: u.hash },
    storage: sessionStorage,
    replaceUrl: vi.fn(),
    navigate: vi.fn(),
    emulator: options.emulator ?? false,
    signInWithToken: vi.fn(async () => {}),
    devSignIn: vi.fn(async () => {}),
    completeDevSignIn: vi.fn(async () => options.devResult ?? false),
  } satisfies SignInDeps;
  return deps;
}

beforeEach(() => sessionStorage.clear());

describe("readFragment", () => {
  it.each([
    ["", "s", null],
    ["#", "s", null],
    ["#foo=bar", "s", null],
    ["#access_token=t1&state=s", "s", { token: "t1" }],
    ["#access_token=t1&state=other", "s", { error: "Session de connexion invalide — cliquez à nouveau sur « Se connecter »." }],
    ["#access_token=t1", null, { error: "Session de connexion invalide — cliquez à nouveau sur « Se connecter »." }],
    ["#error=access_denied", "s", { error: "Connexion Google refusée : access_denied" }],
  ])("%j", (hash, state, expected) => {
    expect(readFragment(hash, state)).toEqual(expected);
  });
});

describe("authorizeUrl", () => {
  it("comes back to /competitions, the registered redirect URI, with a token", () => {
    const url = new URL(authorizeUrl("https://alj.example", "abc"));
    expect(url.origin + url.pathname).toBe("https://accounts.google.com/o/oauth2/v2/auth");
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      redirect_uri: "https://alj.example/competitions",
      response_type: "token",
      state: "abc",
      prompt: "select_account",
    });
  });
});

describe("handleSignIn", () => {
  it("does nothing outside /competitions", async () => {
    const deps = setup("/bureau/?login=1#access_token=x&state=y");
    expect(await handleSignIn(deps)).toBeNull();
    expect(deps.replaceUrl).not.toHaveBeenCalled();
    expect(deps.navigate).not.toHaveBeenCalled();
  });

  it("starts the Google sign-in on ?login=1, with a state kept for the way back", async () => {
    const deps = setup("/competitions?login=1");
    await handleSignIn(deps);
    expect(deps.replaceUrl).toHaveBeenCalledWith("/competitions");
    const target = new URL(deps.navigate.mock.calls[0]![0] as string);
    expect(target.searchParams.get("state")).toBe(sessionStorage.getItem("alj_oauth_state"));
  });

  it("signs in with the token Google sent back, then opens the page that asked", async () => {
    sessionStorage.setItem("alj_oauth_state", "s1");
    sessionStorage.setItem(AFTER_LOGIN_KEY, "/bureau/adherents?id=3");
    const deps = setup("/competitions#access_token=tok&state=s1&token_type=Bearer");
    expect(await handleSignIn(deps)).toBeNull();
    expect(deps.replaceUrl).toHaveBeenCalledWith("/competitions"); // token out of the address
    expect(deps.signInWithToken).toHaveBeenCalledWith("tok");
    expect(deps.navigate).toHaveBeenCalledWith("/bureau/adherents?id=3");
    expect(sessionStorage.getItem(AFTER_LOGIN_KEY)).toBeNull();
    expect(sessionStorage.getItem("alj_oauth_state")).toBeNull();
  });

  it.each(["https://evil.example/", "//evil.example/x", "/competitions"])("stays on the page for a return address %s", async (back) => {
    sessionStorage.setItem("alj_oauth_state", "s1");
    sessionStorage.setItem(AFTER_LOGIN_KEY, back);
    const deps = setup("/competitions#access_token=tok&state=s1");
    await handleSignIn(deps);
    expect(deps.navigate).not.toHaveBeenCalled();
  });

  it("reports a refused or forged return without signing in", async () => {
    sessionStorage.setItem("alj_oauth_state", "s1");
    const deps = setup("/competitions#access_token=tok&state=forged");
    expect(await handleSignIn(deps)).toContain("Session de connexion invalide");
    expect(deps.signInWithToken).not.toHaveBeenCalled();
  });

  it("reports a Firebase failure", async () => {
    sessionStorage.setItem("alj_oauth_state", "s1");
    const deps = setup("/competitions#access_token=tok&state=s1");
    deps.signInWithToken.mockRejectedValueOnce(Object.assign(new Error("x"), { code: "auth/unauthorized-domain" }));
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(await handleSignIn(deps)).toContain("Domaine non autorisé");
  });

  it("dev: opens the emulator's account picker, and comes back after it", async () => {
    const start = setup("/competitions?login=1", { emulator: true });
    await handleSignIn(start);
    expect(start.devSignIn).toHaveBeenCalledOnce();
    expect(start.navigate).not.toHaveBeenCalled();

    sessionStorage.setItem(AFTER_LOGIN_KEY, "/bureau/");
    const back = setup("/competitions", { emulator: true, devResult: true });
    await handleSignIn(back);
    expect(back.navigate).toHaveBeenCalledWith("/bureau/");
  });
});
