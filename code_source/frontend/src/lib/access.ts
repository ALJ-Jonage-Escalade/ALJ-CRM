/* Which role may open which page. The server stays the judge of every API call (api_auth.py): this table
   only keeps a role away from screens it cannot use (navigation, Accueil cards, router guards).
   The same split is applied by the pages not migrated yet (web/shared/alj-shell.js, adminOnly). */
import type { AuthState } from "../composables/auth";
import { isStaff, type Role } from "./roles";

/** public: anyone, signed in or not; viewer: any role, read-only accounts too (the competitions, as on the former
    phone page); staff: coaches and admins; admin: admins only. */
export type Access = "public" | "viewer" | "staff" | "admin";

export const HOME = "/bureau/";
/** Query parameter of Accueil naming the admin page a coach was sent back from (router guards). */
export const REFUSED_QUERY = "reserve";

/** Office pages, in menu order. */
export const PAGES = [
  { id: "accueil", icon: "🏠", label: "Accueil", short: "Accueil", href: "/bureau/", access: "staff" },
  { id: "adherents", icon: "👥", label: "Adhérents", short: "Adhérents", href: "/bureau/adherents", access: "staff" },
  { id: "annuaire", icon: "📇", label: "Annuaire", short: "Annuaire", href: "/index", access: "staff" },
  { id: "communications", icon: "✉️", label: "Communications", short: "Messages", href: "/bureau/communications", access: "admin" },
  { id: "competitions", icon: "🏆", label: "Compétitions", short: "Compét.", href: "/bureau/competitions", access: "viewer" },
  { id: "planning", icon: "📅", label: "Planning", short: "Planning", href: "/bureau/planning", access: "staff" },
  { id: "outils", icon: "🛠️", label: "Outils", short: "Outils", href: "/bureau/outils", access: "staff" },
  { id: "parametres", icon: "⚙️", label: "Paramètres", short: "Réglages", href: "/bureau/parametres", access: "admin" },
] as const satisfies readonly { id: string; icon: string; label: string; short: string; href: string; access: Access }[];

export type PageId = (typeof PAGES)[number]["id"];

export function pageAccess(id: PageId): Access {
  return PAGES.find((p) => p.id === id)!.access;
}

export function canOpen(role: Role, access: Access): boolean {
  if (access === "public") return true;
  if (access === "admin") return role === "admin";
  if (access === "viewer") return role !== null;
  return isStaff(role);
}

/**
 * What a page with this access shows for the current session.
 * - allow: the page itself
 * - pending: nothing yet (the session or the role is being checked)
 * - signIn / unverified / noAccess: the gate (sign in, retry, account not allowed in the office)
 * - adminOnly: a staff member on an admin page; the router sends them back to Accueil
 * - offline: a page readable offline (offlineRead), whose role could not be checked because the network is down: it
 *   shows the copy kept on the device for this user, if any (only a user the server let in has one, lib/store.ts)
 */
export type Verdict = "allow" | "pending" | "signIn" | "unverified" | "noAccess" | "adminOnly" | "offline";

export function verdict(state: AuthState, access: Access, offlineRead = false): Verdict {
  if (access === "public") return "allow";
  if (state.status === "loading") return "pending";
  if (state.status === "signedOut") return "signIn";
  if (state.status === "error") return offlineRead && state.offline ? "offline" : "unverified";
  if (canOpen(state.role, access)) return "allow";
  return isStaff(state.role) ? "adminOnly" : "noAccess";
}
