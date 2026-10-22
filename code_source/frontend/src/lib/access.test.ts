import { describe, expect, it } from "vitest";
import type { AuthState } from "../composables/auth";
import { canOpen, pageAccess, PAGES, verdict, type Access, type Verdict } from "./access";
import type { Role } from "./roles";

const USER = { uid: "u1", email: "u@example.org" };
const signedIn = (role: Role): AuthState => ({ status: "signedIn", user: USER, role });

describe("verdict", () => {
  // [session, public, viewer, staff, admin]
  const CASES: [string, AuthState, Verdict, Verdict, Verdict, Verdict][] = [
    ["loading", { status: "loading" }, "allow", "pending", "pending", "pending"],
    ["signed out", { status: "signedOut" }, "allow", "signIn", "signIn", "signIn"],
    ["role not checked", { status: "error", user: USER, message: "x", offline: false }, "allow", "unverified", "unverified", "unverified"],
    ["role not checked, offline", { status: "error", user: USER, message: "x", offline: true }, "allow", "unverified", "unverified", "unverified"],
    ["admin", signedIn("admin"), "allow", "allow", "allow", "allow"],
    ["coach", signedIn("coach"), "allow", "allow", "allow", "adminOnly"],
    ["readonly", signedIn("readonly"), "allow", "allow", "noAccess", "noAccess"],
    ["no role", signedIn(null), "allow", "noAccess", "noAccess", "noAccess"],
  ];

  it.each(CASES)("%s", (_name, state, onPublic, onViewer, onStaff, onAdmin) => {
    expect(verdict(state, "public")).toBe(onPublic);
    expect(verdict(state, "viewer")).toBe(onViewer);
    expect(verdict(state, "staff")).toBe(onStaff);
    expect(verdict(state, "admin")).toBe(onAdmin);
  });
});

describe("verdict of a page readable offline", () => {
  const offline: AuthState = { status: "error", user: USER, message: "x", offline: true };
  it("opens on its offline copy when the role could not be checked for lack of network only", () => {
    expect(verdict(offline, "staff", true)).toBe("offline");
    expect(verdict({ ...offline, offline: false }, "staff", true)).toBe("unverified");
  });
  it.each([
    [{ status: "signedOut" } as AuthState, "signIn"],
    [signedIn("readonly"), "noAccess"],
    [signedIn("coach"), "allow"],
  ])("otherwise as any page", (state, expected) => {
    expect(verdict(state, "staff", true)).toBe(expected);
  });
});

describe("canOpen", () => {
  const CASES: [Role, Access, boolean][] = [
    ["admin", "admin", true], ["admin", "staff", true],
    ["coach", "admin", false], ["coach", "staff", true],
    ["readonly", "admin", false], ["readonly", "staff", false], ["readonly", "viewer", true], ["readonly", "public", true],
    [null, "viewer", false], [null, "staff", false], [null, "public", true],
  ];
  it.each(CASES)("%s on a %s page: %s", (role, access, expected) => {
    expect(canOpen(role, access)).toBe(expected);
  });
});

describe("PAGES", () => {
  it("keeps Paramètres and Communications for admins", () => {
    expect(PAGES.filter((p) => p.access === "admin").map((p) => p.id)).toEqual(["communications", "parametres"]);
    expect(pageAccess("accueil")).toBe("staff");
  });
});
