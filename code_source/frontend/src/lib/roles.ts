/* Roles as answered by GET /api/me: the server (api_auth.py) is the only judge, pages only display them. */
import type { Schemas } from "./client";

/** The contract's role (null: signed in without access); a new server role breaks the tables below at build time. */
export type Role = Schemas["Me"]["role"];

/** The role names, as the administration lists them. */
export const ROLE_NAME: Record<NonNullable<Role>, string> = { admin: "Administrateur", coach: "Coach", readonly: "Lecture seule" };
const ROLE_ICON: Record<NonNullable<Role>, string> = { admin: "🛡️", coach: "🏃", readonly: "👁️" };

/** « 🛡️ Administrateur », the badge of the signed-in account. */
export function roleLabel(role: Role): string {
  return role ? `${ROLE_ICON[role]} ${ROLE_NAME[role]}` : "⛔ Non autorisé";
}

/** A role the server may answer, for reading an answer that is not typed yet. */
export function isRole(value: unknown): value is Role {
  return value === null || (typeof value === "string" && Object.hasOwn(ROLE_NAME, value));
}

/** The office portal is for coaches and administrators. */
export function isStaff(role: Role): boolean {
  return role === "admin" || role === "coach";
}

/** Administrators: access management, member edits, settings, imports. */
export function isAdmin(role: Role): boolean {
  return role === "admin";
}
