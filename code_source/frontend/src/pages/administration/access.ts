/* What the Accès sub-page shows of the access list, its requests and history: labels, dates, the add form check. */
import { looksLikeEmail } from "../../lib/email";
import { formatDate, formatDateTime, parseDate } from "../../lib/format";
import type { Schemas } from "../../lib/client";

export type AccessRole = Schemas["AccessEntry"]["role"];
export type HistoryAction = Schemas["AccessHistoryEntry"]["action"];

const ROLE_NAMES: Record<AccessRole, string> = { admin: "Administrateur", coach: "Coach", readonly: "Lecture seule" };

/** The roles an admin may give, highest first. */
export const ROLE_OPTIONS: readonly { value: AccessRole; label: string }[] = (["admin", "coach", "readonly"] as const).map((role) => ({
  value: role,
  label: ROLE_NAMES[role],
}));

const ACTION_LABELS: Record<HistoryAction, string> = {
  added: "Accès ajouté",
  role_changed: "Rôle modifié",
  name_changed: "Nom modifié",
  removed: "Accès retiré",
  request_granted: "Demande acceptée",
  request_dismissed: "Demande ignorée",
  bootstrap: "Administrateur initial",
};

/** The role of this option value, or null for anything else. */
export function accessRole(value: string): AccessRole | null {
  return ROLE_OPTIONS.find((option) => option.value === value)?.value ?? null;
}

export function roleName(role: AccessRole | null | undefined): string {
  return role ? ROLE_NAMES[role] : "—";
}

export function actionLabel(action: HistoryAction): string {
  return ACTION_LABELS[action];
}

/** « Coach → Administrateur », « → Coach » for a new access, « Coach → » for a removal, empty when no role changed. */
export function roleChange(entry: Pick<Schemas["AccessHistoryEntry"], "old_role" | "new_role" | "action">): string {
  if (entry.action === "name_changed" || (!entry.old_role && !entry.new_role)) {
    return "";
  }
  return `${entry.old_role ? roleName(entry.old_role) : ""} → ${entry.new_role ? roleName(entry.new_role) : ""}`.trim();
}

/** Who made a change: the admin's address, « Démarrage du serveur » for the bootstrap admin. */
export function authorLabel(author: string): string {
  return author === "bootstrap" ? "Démarrage du serveur" : author;
}

/** « 30/10/2026 » or « Jamais ». */
export function lastSignIn(at: string | null | undefined): string {
  const date = parseDate(at);
  return date ? formatDate(date) : "Jamais";
}

/** « 30/10/2026 09:15 », or the text as is when it is not a date. */
export function dateTime(at: string): string {
  const date = parseDate(at);
  return date ? formatDateTime(date) : at;
}

/** Why the add form can't be sent (empty when it can); the server checks again. */
export function addFormError(email: string): string {
  const address = email.trim();
  if (!address) {
    return "Saisissez l'adresse e-mail Google de la personne.";
  }
  return looksLikeEmail(address) ? "" : "Adresse e-mail invalide.";
}

/** The signed-in admin's own entry: the server refuses to remove or demote it, the page says so before. */
export function isOwnEntry(entryEmail: string, signedInEmail: string): boolean {
  return entryEmail.trim().toLowerCase() === signedInEmail.trim().toLowerCase();
}
