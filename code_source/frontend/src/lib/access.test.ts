import { describe, expect, it } from "vitest";
import type { AuthState } from "../composables/auth";
import { canOpen, pageAccess, PAGES, verdict, type Access, type Verdict } from "./access";
import type { Role } from "./roles";

const USER = { uid: "u1", email: "u@example.org" };
const signedIn = (role: Role): AuthState => ({ status: "signedIn", user: USER, role });

describe("verdict", () => {
  // [session, public, staff, admin]
  const CASES: [string, AuthState, Verdict, Verdict, Verdict][] = [
    ["loading", { status: "loading" }, "allow", "pending", "pending"],
    ["signed out", { status: "signedOut" }, "allow", "signIn", "signIn"],
    ["role not checked", { status: "error", user: USER, message: "x" }, "allow", "unverified", "unverified"],
    ["admin", signedIn("admin"), "allow", "allow", "allow"],
    ["coach", signedIn("coach"), "allow", "allow", "adminOnly"],
    ["readonly", signedIn("readonly"), "allow", "noAccess", "noAccess"],
    ["no role", signedIn(null), "allow", "noAccess", "noAccess"],
  ];

  it.each(CASES)("%s", (_name, state, onPublic, onStaff, onAdmin) => {
    expect(verdict(state, "public")).toBe(onPublic);
    expect(verdict(state, "staff")).toBe(onStaff);
    expect(verdict(state, "admin")).toBe(onAdmin);
  });
});

describe("canOpen", () => {
  const CASES: [Role, Access, boolean][] = [
    ["admin", "admin", true], ["admin", "staff", true],
    ["coach", "admin", false], ["coach", "staff", true],
    ["readonly", "admin", false], ["readonly", "staff", false], ["readonly", "public", true],
    [null, "staff", false], [null, "public", true],
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
