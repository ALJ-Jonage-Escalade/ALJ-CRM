/* Which role may open which page. The server stays the judge of every API call (api_auth.py): this table
   only keeps a role away from screens it cannot use (navigation, Accueil cards, router guards). */
import type { AuthState } from "../composables/auth";
import { isAdmin, isStaff, type Role } from "./roles";

/** public: anyone, signed in or not; viewer: every role, read-only accounts too (the competitions, as on the former
    phone page); staff: coaches and admins; admin: admins only. */
export type Access = "public" | "viewer" | "staff" | "admin";

export const HOME = "/bureau/";
/** Query parameter of Accueil naming the admin page a coach was sent back from (router guards). */
export const REFUSED_QUERY = "reserve";

/** Screens on which a page is listed (menu, Accueil cards), from the same breakpoint as the menu (`md`): on a phone,
    only Accueil, Compétitions and the directory; the office pages are listed on a computer only. Hidden by CSS only:
    every address still opens on any screen. */
export type Screen = "any" | "phone" | "desktop";

/** What a sub-page shows offline, when the role cannot be checked: read — the copy kept on the device; staffCopy — only
    on a device the parent page says holds a staff copy (Compétitions: the competitors' contacts, never kept for other
    roles); none — nothing, online only (listed disabled on a staff device). */
export type SubOffline = "read" | "staffCopy" | "none";

/** A sub-page of an office page, listed under it in the menu (plans/sub-menus.md). The first one is the page's index
    route (empty path): the page's own address opens it. */
export interface SubPage {
  id: string;
  label: string;
  path: string;
  access: Access;
  offline: SubOffline;
}

/** Office pages, in menu order. offlineRead: the page shows the copy kept on the device when the role cannot be checked
    for lack of network (verdict "offline"). */
export const PAGES = [
  { id: "accueil", icon: "🏠", label: "Accueil", href: "/bureau/", access: "staff", screen: "any", offlineRead: false },
  {
    id: "adherents",
    icon: "👥",
    label: "Adhérents",
    href: "/bureau/adherents",
    access: "staff",
    screen: "desktop",
    offlineRead: false,
  },
  { id: "annuaire", icon: "📇", label: "Annuaire", href: "/index", access: "staff", screen: "phone", offlineRead: true },
  {
    id: "communications",
    icon: "✉️",
    label: "Communications",
    href: "/bureau/communications",
    access: "admin",
    screen: "desktop",
    offlineRead: false,
    // Online only: neither the templates nor the sends are kept on the device
    children: [
      { id: "modeles", label: "Modèles", path: "", access: "admin", offline: "none" },
      { id: "historique", label: "Historique des envois", path: "historique", access: "admin", offline: "none" },
    ],
  },
  {
    id: "competitions",
    icon: "🏆",
    label: "Compétitions",
    href: "/bureau/competitions",
    access: "viewer",
    screen: "any",
    offlineRead: true,
    children: [
      { id: "competitions", label: "Compétitions", path: "", access: "viewer", offline: "read" },
      { id: "helloasso", label: "HelloAsso", path: "helloasso", access: "staff", offline: "none" },
      { id: "bilan", label: "Bilan", path: "bilan", access: "staff", offline: "staffCopy" },
      { id: "coachs", label: "Coachs", path: "coachs", access: "staff", offline: "staffCopy" },
    ],
  },
  {
    id: "planning",
    icon: "📅",
    label: "Planning",
    href: "/bureau/planning",
    access: "staff",
    screen: "desktop",
    offlineRead: false,
    children: [
      { id: "semaine", label: "Vue semaine", path: "", access: "staff", offline: "none" },
      { id: "tableau", label: "Tableau des créneaux", path: "tableau", access: "staff", offline: "none" },
    ],
  },
  {
    id: "outils",
    icon: "🛠️",
    label: "Outils",
    href: "/bureau/outils",
    access: "staff",
    screen: "desktop",
    offlineRead: false,
    children: [
      { id: "stats", label: "Statistiques", path: "", access: "staff", offline: "none" },
      { id: "map", label: "Carte", path: "map", access: "staff", offline: "none" },
      { id: "presence", label: "Fiches de présence", path: "presence", access: "staff", offline: "none" },
      { id: "ffme", label: "Export FFME", path: "ffme", access: "staff", offline: "none" },
      { id: "ffme-import", label: "Import FFME", path: "ffme-import", access: "admin", offline: "none" },
      { id: "helloasso-import", label: "Import HelloAsso", path: "helloasso-import", access: "admin", offline: "none" },
      { id: "cles", label: "Clés", path: "cles", access: "staff", offline: "none" },
    ],
  },
  {
    id: "parametres",
    icon: "⚙️",
    label: "Paramètres",
    href: "/bureau/parametres",
    access: "admin",
    screen: "desktop",
    offlineRead: false,
    // Online only: the settings are never kept on the device
    children: [
      { id: "general", label: "Général", path: "", access: "admin", offline: "none" },
      { id: "campagnes", label: "Campagne HelloAsso", path: "campagnes", access: "admin", offline: "none" },
    ],
  },
  {
    id: "administration",
    icon: "🔐",
    label: "Administration",
    href: "/bureau/administration",
    access: "admin",
    screen: "desktop",
    offlineRead: false,
    // Online only: who has access is never kept on the device
    children: [{ id: "acces", label: "Accès", path: "", access: "admin", offline: "none" }],
  },
] as const satisfies readonly {
  id: string;
  icon: string;
  label: string;
  href: string;
  access: Access;
  screen: Screen;
  offlineRead: boolean;
  children?: readonly SubPage[];
}[];

export type PageId = (typeof PAGES)[number]["id"];

export function pageAccess(id: PageId): Access {
  return PAGES.find((p) => p.id === id)!.access;
}

export function pageScreen(id: PageId): Screen {
  return PAGES.find((p) => p.id === id)!.screen;
}

/** The sub-pages of an office page, in menu order (none for a page without sub-menu). */
export function subPages(id: PageId): readonly SubPage[] {
  const page = PAGES.find((p) => p.id === id)!;
  return "children" in page ? page.children : [];
}

/** Address of a sub-page: the page's own for its index route. */
export function subHref(id: PageId, sub: SubPage): string {
  const href = PAGES.find((p) => p.id === id)!.href;
  return sub.path ? `${href}/${sub.path}` : href;
}

/**
 * What the menu does with a sub-page for the current session (the page's own verdict is checked first).
 * - allow: listed, opens
 * - disabled: listed, does not open (online only, offline on a staff device)
 * - hidden: not listed; opened by its address, the page sends back to its index route
 * - pending: not known yet (session loading, or the parent page still reading what the device holds: staffCopy null)
 */
export type SubVerdict = "allow" | "disabled" | "hidden" | "pending";

export function subVerdict(state: AuthState, sub: SubPage, staffCopy: boolean | null): SubVerdict {
  if (state.status === "signedIn") {
    return canOpen(state.role, sub.access) ? "allow" : "hidden";
  }
  if (state.status !== "error" || !state.offline) {
    return "pending"; // the page shows its gate
  }
  if (sub.offline === "read") {
    return "allow";
  }
  if (staffCopy === null) {
    return "pending";
  }
  if (!staffCopy) {
    return "hidden";
  }
  return sub.offline === "staffCopy" ? "allow" : "disabled";
}

/** The pages readable offline (the gate links to them when the role cannot be checked for lack of network). */
export const OFFLINE_PAGES = PAGES.filter((p) => p.offlineRead);

// Whole class names, for Tailwind to find them in this file
const SHOWN: Record<"flex" | "block", Record<Screen, string>> = {
  flex: { any: "flex", phone: "flex md:hidden", desktop: "hidden md:flex" },
  block: { any: "block", phone: "block md:hidden", desktop: "hidden md:block" },
};

/** Display classes of a link listed on these screens only. */
export function shownOn(screen: Screen, display: "flex" | "block"): string {
  return SHOWN[display][screen];
}

export function canOpen(role: Role, access: Access): boolean {
  if (access === "public") {
    return true;
  }
  if (access === "admin") {
    return isAdmin(role);
  }
  if (access === "viewer") {
    return role !== null;
  }
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
  if (access === "public") {
    return "allow";
  }
  if (state.status === "loading") {
    return "pending";
  }
  if (state.status === "signedOut") {
    return "signIn";
  }
  if (state.status === "error") {
    return offlineRead && state.offline ? "offline" : "unverified";
  }
  if (canOpen(state.role, access)) {
    return "allow";
  }
  return isStaff(state.role) ? "adminOnly" : "noAccess";
}

/** The verdict of an office page, readable offline or not as PAGES says. */
export function pageVerdict(state: AuthState, id: PageId): Verdict {
  const page = PAGES.find((p) => p.id === id)!;
  return verdict(state, page.access, page.offlineRead);
}
