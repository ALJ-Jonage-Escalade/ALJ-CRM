/* The e-mail log of a competition as its page shows it (server: domain/email_log.py): what to write on the header,
   and the French names of the kinds. */
import type { Schemas } from "../../../lib/client";
import { formatDate, formatDateTime, parseDate } from "../../../lib/format";

export type EmailLog = Schemas["CompetitionEmailLog"];
export type EmailLogEntry = Schemas["EmailLogEntry"];
type Kind = EmailLogEntry["kind"];

export const KIND_LABELS: Record<Kind, string> = {
  competition_email: "E-mail aux compétiteurs",
  member_email: "E-mail aux adhérents",
  competition_all_paid: "Interne : tous les paiements reçus",
  results_batch: "Interne : résultats de compétition",
  attestation: "Attestation de paiement",
  access_invitation: "Invitation au bureau",
};

/** E-mails to the club itself, listed in the history but never counted as a contact with the families. */
export function isInternal(kind: Kind): boolean {
  return kind === "competition_all_paid" || kind === "results_batch";
}

/**
 * What a date line shows:
 * - date: the last e-mail that left; failed: the competitor's latest attempt failed; none: never e-mailed;
 * - unavailable: no answer from the server and no copy on the device (never « none »: nobody may read « never contacted »);
 * - loading: nothing known yet, nothing shown.
 */
export type ContactState =
  { kind: "date"; at: string } | { kind: "failed"; at: string | null } | { kind: "none" } | { kind: "unavailable" } | { kind: "loading" };

/** The log of the page: the answer (or its copy), and whether reading it failed with nothing to show. */
export interface LogView {
  log: EmailLog | null;
  failed: boolean;
}

function unknownState(view: LogView): ContactState {
  return view.failed ? { kind: "unavailable" } : { kind: "loading" };
}

export function lastSendState(view: LogView): ContactState {
  if (!view.log) {
    return unknownState(view);
  }
  const at = view.log.summary.last_competitor_email_at;
  return at ? { kind: "date", at } : { kind: "none" };
}

export function failedCount(entry: EmailLogEntry): number {
  return (entry.recipients ?? []).filter((r) => r.status === "failed").length;
}

/** « 24/10/2026 » for a server date. */
export function dayOf(at: string): string {
  const date = parseDate(at);
  return date ? formatDate(date) : at;
}

/** « 24/10/2026 14:05 » for a server date. */
export function momentOf(at: string): string {
  const date = parseDate(at);
  return date ? formatDateTime(date) : at;
}
