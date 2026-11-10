/* What the Accès sub-page shows of the access list, its invitations and history: labels, dates, the invite form check. */
import { looksLikeEmail } from "../../lib/email";
import { formatDate, formatDateTime, parseDate } from "../../lib/format";
import type { Schemas } from "../../lib/client";
import { ROLE_NAME } from "../../lib/roles";

export type AccessEntry = Schemas["AccessEntry"];
export type AccessRole = AccessEntry["role"];
export type HistoryAction = Schemas["AccessHistoryEntry"]["action"];

/** The roles an admin may give, highest first. */
export const ROLE_OPTIONS: readonly { value: AccessRole; label: string }[] = (["admin", "coach", "readonly"] as const).map((role) => ({
  value: role,
  label: ROLE_NAME[role],
}));

const ACTION_LABELS: Record<HistoryAction, string> = {
  invited: "Invitation",
  invitation_resent: "Invitation renvoyée",
  added: "Accès ajouté",
  role_changed: "Rôle modifié",
  name_changed: "Nom modifié",
  removed: "Accès retiré",
  bootstrap: "Administrateur initial",
};

/** The role of this option value, or null for anything else. */
export function accessRole(value: string): AccessRole | null {
  return ROLE_OPTIONS.find((option) => option.value === value)?.value ?? null;
}

export function roleName(role: AccessRole | null | undefined): string {
  return role ? ROLE_NAME[role] : "—";
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
export function lastSignInText(at: string | null | undefined): string {
  const date = parseDate(at);
  return date ? formatDate(date) : "Jamais";
}

/** « 30/10/2026 09:15 », or the text as is when it is not a date. */
export function dateTimeText(at: string): string {
  const date = parseDate(at);
  return date ? formatDateTime(date) : at;
}

/** Where an entry stands: an access in use, an invitation still open, or one nobody accepted in time (no role then). */
export type AccessStatus = "active" | "invited" | "expired";

export function accessStatus(entry: Pick<AccessEntry, "invitation_expires_at">, now: Date): AccessStatus {
  if (!entry.invitation_expires_at) {
    return "active";
  }
  const expires = parseDate(entry.invitation_expires_at);
  return expires && expires > now ? "invited" : "expired";
}

/** « Actif », « Invité · expire le 06/11/2026 », « Invitation expirée le 06/11/2026 ». */
export function statusLabel(entry: Pick<AccessEntry, "invitation_expires_at">, now: Date): string {
  const expires = parseDate(entry.invitation_expires_at);
  const day = expires ? ` le ${formatDate(expires)}` : "";
  switch (accessStatus(entry, now)) {
    case "active":
      return "Actif";
    case "invited":
      return `Invité · expire${day}`;
    case "expired":
      return `Invitation expirée${day}`;
  }
}

/** An open or expired invitation whose last e-mail did not go out. */
export function emailNotSent(entry: Pick<AccessEntry, "invitation_expires_at" | "invitation_sent_at">): boolean {
  return Boolean(entry.invitation_expires_at) && !entry.invitation_sent_at;
}

/** The toast after an invitation or a resend: done, or kept without its e-mail and why. */
export function invitationMessage(invitation: Schemas["AccessInvitation"]): string {
  const email = invitation.entry.email;
  if (invitation.email_sent) {
    return `✉️ Invitation envoyée à ${email} (${roleName(invitation.entry.role)}).`;
  }
  return `⚠️ Invitation enregistrée pour ${email}, mais l'e-mail n'a pas pu être envoyé : ${invitation.email_error ?? "erreur inconnue"}. Utilisez « Renvoyer » ou prévenez la personne vous-même.`;
}

/** Why the invite form can't be sent (empty when it can); the server checks again. */
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
