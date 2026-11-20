/* The e-mail log as the pages show it (server: domain/email_log.py): French names of the kinds, internal e-mails,
   failures and dates. Shared by the competition page and Communications › Historique des envois. */
import type { Schemas } from "./client";
import { formatDateTime, parseDate } from "./format";
import { normKey } from "./text";

export type EmailLogEntry = Schemas["EmailLogEntry"];
export type EmailKind = EmailLogEntry["kind"];

export const KIND_LABELS: Record<EmailKind, string> = {
  competition_email: "E-mail aux compétiteurs",
  member_email: "E-mail aux adhérents",
  competition_all_paid: "Interne : tous les paiements reçus",
  results_batch: "Interne : résultats de compétition",
  attestation: "Attestation de paiement",
  access_invitation: "Invitation au bureau",
  correction_request: "Adhésion : demande de correction",
};

/** E-mails to the club itself, listed in the history but never counted as a contact with the families. */
export function isInternal(kind: EmailKind): boolean {
  return kind === "competition_all_paid" || kind === "results_batch";
}

export function failedCount(entry: EmailLogEntry): number {
  return (entry.recipients ?? []).filter((r) => r.status === "failed").length;
}

/** « 24/10/2026 14:05 » for a server date. */
export function momentOf(at: string): string {
  const date = parseDate(at);
  return date ? formatDateTime(date) : at;
}

/** The filters of Historique des envois: one kind ("" for all) and one search text ("" for none). */
export interface EmailLogFilter {
  kind: EmailKind | "";
  search: string;
}

/** The sends of this kind whose recipients (name or address), author, subject, template or competition name contain
    the search text, accents and case ignored. */
export function filterEntries(
  entries: readonly EmailLogEntry[],
  filter: EmailLogFilter,
  competitionNames: Readonly<Record<number, string>>,
): EmailLogEntry[] {
  const search = normKey(filter.search);
  return entries.filter((entry) => {
    if (filter.kind && entry.kind !== filter.kind) {
      return false;
    }
    const texts = [
      entry.author,
      entry.subject,
      entry.template,
      ...(entry.recipients ?? []).flatMap((r) => [r.name, r.email]),
      ...(entry.competition_ids ?? []).map((id) => competitionNames[id]),
    ];
    return !search || texts.some((text) => normKey(text).includes(search));
  });
}
