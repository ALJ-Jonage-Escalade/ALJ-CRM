import { describe, expect, it, vi } from "vitest";
import { AFTER_LOGIN_KEY, createAuth, LOGIN_URL, type AuthDeps, type SessionUser } from "./auth";

const ALBUS: SessionUser = { uid: "u-albus", email: "albus@alj-escalade.fr" };
const FILCH: SessionUser = { uid: "u-filch", email: "argus.filch@hogwarts.example" };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Fake Firebase session: emit(user) plays onAuthStateChanged. */
function setup(fetchMe: AuthDeps["fetchMe"], onNetworkBack?: AuthDeps["onNetworkBack"]) {
  let listener: (user: SessionUser | null) => void = () => {};
  const deps = {
    onUserChange: vi.fn((cb: (user: SessionUser | null) => void) => {
      listener = cb;
      return () => {};
    }),
    fetchMe: vi.fn(fetchMe),
    signOut: vi.fn(async () => {}),
    storage: { setItem: vi.fn() },
    navigate: vi.fn(),
    currentPath: () => "/bureau/?x=1",
    onNetworkBack,
  };
  const auth = createAuth(deps);
  /** Firebase reports a user change; resolves once the state is settled. */
  const emit = async (user: SessionUser | null) => {
    listener(user);
    await vi.waitFor(() => expect(auth.state.value.status).not.toBe("loading"));
  };
  return { auth, deps, emit, change: (user: SessionUser | null) => listener(user) };
}

describe("createAuth", () => {
  it("is loading until Firebase answers", () => {
    const { auth } = setup(async () => json({ email: "", role: null }));
    expect(auth.state.value).toEqual({ status: "loading" });
  });

  it("is signed out without a user, and does not call the server", async () => {
    const { auth, deps, emit } = setup(async () => json({}));
    await emit(null);
    expect(auth.state.value).toEqual({ status: "signedOut" });
    expect(deps.fetchMe).not.toHaveBeenCalled();
  });

  it.each(["admin", "coach", "readonly", null] as const)("takes the role %s from /api/me", async (role) => {
    const { auth, emit } = setup(async () => json({ email: ALBUS.email, role }));
    await emit(ALBUS);
    expect(auth.state.value).toEqual({ status: "signedIn", user: ALBUS, role });
  });

  it("reports a refused session", async () => {
    const { auth, emit } = setup(async () => json({ status: "error" }, 401));
    await emit(ALBUS);
    expect(auth.state.value).toEqual({
      status: "error",
      user: ALBUS,
      message: "Session refusée par le serveur : reconnectez-vous.",
      offline: false,
    });
  });

  const UNREACHABLE = "Serveur injoignable : vérifiez la connexion réseau.";
  it.each([
    ["a server error", async () => json({}, 500), "Le serveur ne répond pas correctement (erreur 500).", false],
    [
      "no network",
      async () => {
        throw new TypeError("Failed to fetch");
      },
      UNREACHABLE,
      true,
    ],
    [
      "no network to renew the token",
      async () => {
        throw Object.assign(new Error("x"), { code: "auth/network-request-failed" });
      },
      UNREACHABLE,
      true,
    ],
    ["an unknown role", async () => json({ email: "x", role: "superuser" }), "Réponse inattendue du serveur.", false],
    ["a body that is not JSON", async () => new Response("<html>", { status: 200 }), "Réponse inattendue du serveur.", false],
  ])("reports %s without granting access", async (_case, fetchMe, message, offline) => {
    const { auth, emit } = setup(fetchMe);
    await emit(ALBUS);
    expect(auth.state.value).toEqual({ status: "error", user: ALBUS, message, offline });
  });

  it("asks the server again when the network comes back, only while the role is unknown", async () => {
    let calls = 0;
    let networkBack: () => void = () => {};
    const { auth, deps, emit } = setup(
      async () => {
        if (++calls === 1) {
          throw new TypeError("Failed to fetch");
        }
        return json({ email: ALBUS.email, role: "coach" });
      },
      (cb) => {
        networkBack = cb;
        return () => {};
      },
    );
    await emit(ALBUS);
    expect(auth.state.value.status).toBe("error");
    networkBack();
    await vi.waitFor(() => expect(auth.state.value).toEqual({ status: "signedIn", user: ALBUS, role: "coach" }));
    networkBack();
    await new Promise((r) => setTimeout(r, 0));
    expect(deps.fetchMe).toHaveBeenCalledTimes(2);
  });

  it("asks the server again on retry", async () => {
    let calls = 0;
    const { auth, emit } = setup(async () => (++calls === 1 ? json({}, 503) : json({ email: ALBUS.email, role: "coach" })));
    await emit(ALBUS);
    expect(auth.state.value.status).toBe("error");
    await auth.retry();
    expect(auth.state.value).toEqual({ status: "signedIn", user: ALBUS, role: "coach" });
  });

  it("drops the answer meant for a previous user", async () => {
    let releaseAlbus: (r: Response) => void = () => {};
    const { auth, change } = setup(
      (): Promise<Response> =>
        new Promise((resolve) => {
          releaseAlbus = resolve;
        }),
    );
    change(ALBUS); // /api/me still on its way
    change(null); // signed out meanwhile
    expect(auth.state.value).toEqual({ status: "signedOut" });
    releaseAlbus(json({ email: ALBUS.email, role: "admin" }));
    await new Promise((r) => setTimeout(r, 0));
    expect(auth.state.value).toEqual({ status: "signedOut" });
  });

  it("keeps the e-mail of the session when the server sends none", async () => {
    const { auth, emit } = setup(async () => json({ email: "", role: null }));
    await emit(FILCH);
    expect(auth.state.value).toEqual({ status: "signedIn", user: FILCH, role: null });
  });

  it("signs in through the competitions page and comes back to the current page", () => {
    const { auth, deps } = setup(async () => json({}));
    auth.login();
    expect(deps.storage.setItem).toHaveBeenCalledWith(AFTER_LOGIN_KEY, "/bureau/?x=1");
    expect(deps.navigate).toHaveBeenCalledWith(LOGIN_URL);
  });

  it("signs out through Firebase, even when it fails", async () => {
    const { auth, deps } = setup(async () => json({}));
    deps.signOut.mockRejectedValueOnce(new Error("network"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await expect(auth.logout()).resolves.toBeUndefined();
    expect(deps.signOut).toHaveBeenCalledOnce();
    warn.mockRestore();
  });
});
