import { describe, expect, it } from "vitest";
import type { AuthState } from "../composables/auth";
import {
  canOpen,
  OFFLINE_PAGES,
  pageVerdict,
  shownOn,
  subHref,
  subPages,
  subVerdict,
  verdict,
  type Access,
  type SubOffline,
  type SubPage,
  type SubVerdict,
  type Verdict,
} from "./access";
import type { Role } from "./roles";

const USER = { uid: "u1", email: "u@example.org" };
const signedIn = (role: Role): AuthState => ({ status: "signedIn", user: USER, role });

describe("verdict", () => {
  // [session, public, viewer, staff, admin]
  const CASES: [string, AuthState, Verdict, Verdict, Verdict, Verdict][] = [
    ["loading", { status: "loading" }, "allow", "pending", "pending", "pending"],
    ["signed out", { status: "signedOut" }, "allow", "signIn", "signIn", "signIn"],
    ["role not checked", { status: "error", user: USER, message: "x", offline: false }, "allow", "unverified", "unverified", "unverified"],
    [
      "role not checked, offline",
      { status: "error", user: USER, message: "x", offline: true },
      "allow",
      "unverified",
      "unverified",
      "unverified",
    ],
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
    [{ status: "signedOut" } satisfies AuthState, "signIn"],
    [signedIn("readonly"), "noAccess"],
    [signedIn("coach"), "allow"],
  ])("otherwise as any page", (state, expected) => {
    expect(verdict(state, "staff", true)).toBe(expected);
  });
});

describe("pageVerdict", () => {
  const offline: AuthState = { status: "error", user: USER, message: "x", offline: true };
  it("reads offline only the pages PAGES marks so", () => {
    expect(OFFLINE_PAGES.map((p) => p.id)).toEqual(["annuaire", "competitions"]);
    expect(pageVerdict(offline, "annuaire")).toBe("offline");
    expect(pageVerdict(offline, "competitions")).toBe("offline");
    expect(pageVerdict(offline, "planning")).toBe("unverified");
  });
});

describe("canOpen", () => {
  const CASES: [Role, Access, boolean][] = [
    ["admin", "admin", true],
    ["admin", "staff", true],
    ["coach", "admin", false],
    ["coach", "staff", true],
    ["readonly", "admin", false],
    ["readonly", "staff", false],
    ["readonly", "viewer", true],
    ["readonly", "public", true],
    [null, "viewer", false],
    [null, "staff", false],
    [null, "public", true],
  ];
  it.each(CASES)("%s on a %s page: %s", (role, access, expected) => {
    expect(canOpen(role, access)).toBe(expected);
  });
});

describe("shownOn", () => {
  it("hides a link from the md breakpoint up, or below it", () => {
    expect(shownOn("any", "flex")).toBe("flex");
    expect(shownOn("phone", "flex")).toBe("flex md:hidden");
    expect(shownOn("desktop", "block")).toBe("hidden md:block");
  });
});

describe("subVerdict", () => {
  const offline: AuthState = { status: "error", user: USER, message: "x", offline: true };
  const sub = (access: Access, mode: SubOffline): SubPage => ({ id: "s", label: "S", path: "s", access, offline: mode });

  it.each<[Role, Access, SubVerdict]>([
    ["admin", "admin", "allow"],
    ["coach", "admin", "hidden"],
    ["coach", "staff", "allow"],
    ["readonly", "staff", "hidden"],
    ["readonly", "viewer", "allow"],
  ])("signed in as %s, on a %s sub-page: %s", (role, access, expected) => {
    expect(subVerdict(signedIn(role), sub(access, "none"), false)).toBe(expected);
  });

  it.each<[SubOffline, boolean | null, SubVerdict]>([
    ["read", false, "allow"],
    ["read", null, "allow"],
    ["staffCopy", true, "allow"],
    ["staffCopy", false, "hidden"],
    ["staffCopy", null, "pending"],
    ["none", true, "disabled"],
    ["none", false, "hidden"],
    ["none", null, "pending"],
  ])("offline, %s with a staff copy %s: %s", (mode, staffCopy, expected) => {
    expect(subVerdict(offline, sub("staff", mode), staffCopy)).toBe(expected);
  });

  it("waits while the session loads or the role is not checked online", () => {
    expect(subVerdict({ status: "loading" }, sub("viewer", "read"), true)).toBe("pending");
    expect(subVerdict({ status: "error", user: USER, message: "x", offline: false }, sub("viewer", "read"), true)).toBe("pending");
  });
});

describe("sub-pages", () => {
  it("open the competitions list on the page's own address", () => {
    const [index, ...others] = subPages("competitions");
    expect(index && subHref("competitions", index)).toBe("/bureau/competitions");
    expect(others.map((s) => subHref("competitions", s))).toEqual([
      "/bureau/competitions/helloasso",
      "/bureau/competitions/bilan",
      "/bureau/competitions/coachs",
    ]);
    expect(subPages("communications")).toEqual([]);
  });

  it("split the settings into Général and Campagne HelloAsso, for admins online only", () => {
    const settings = subPages("parametres");
    expect(settings.map((s) => [s.label, subHref("parametres", s)])).toEqual([
      ["Général", "/bureau/parametres"],
      ["Campagne HelloAsso", "/bureau/parametres/campagnes"],
    ]);
    expect(settings.every((s) => s.access === "admin" && s.offline === "none")).toBe(true);
  });
});
