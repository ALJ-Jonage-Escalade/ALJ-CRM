/* The e-mail log of a competition as its page shows it (server: domain/email_log.py): what to write on each competitor's
   row and the sends that included a competitor (kinds and shared helpers: lib/emailLog.ts). */
import type { Schemas } from "../../../lib/client";
import type { EmailLogEntry } from "../../../lib/emailLog";
import { formatDate, parseDate } from "../../../lib/format";
import type { Row } from "../competitions";

export type EmailLog = Schemas["CompetitionEmailLog"];

/**
 * What a date line shows:
 * - date: the last e-mail that left; failed: the competitor's latest attempt failed; none: never e-mailed;
 * - unavailable: no answer from the server and no copy on the device (never « none »: nobody may read « never contacted »);
 * - loading: nothing known yet, nothing shown.
 */
export type ContactState =
  { kind: "date"; at: string } | { kind: "failed" } | { kind: "none" } | { kind: "unavailable" } | { kind: "loading" };

/** The log of the page: the answer (or its copy), and whether reading it failed with nothing to show. */
export interface LogView {
  log: EmailLog | null;
  failed: boolean;
}

function unknownState(view: LogView): ContactState {
  return view.failed ? { kind: "unavailable" } : { kind: "loading" };
}

/** A recipient or summary item is this competitor: same member, else same address when the row has no member. */
function isCompetitor(item: { member_id?: number | null; email?: string }, row: Pick<Row, "adherent_id" | "email">): boolean {
  if (row.adherent_id != null) {
    return item.member_id === row.adherent_id;
  }
  const email = (row.email ?? "").trim().toLowerCase();
  return !!email && (item.email ?? "").trim().toLowerCase() === email;
}

export function competitorContact(view: LogView, row: Pick<Row, "adherent_id" | "email">): ContactState {
  if (!view.log) {
    return unknownState(view);
  }
  const contact = (view.log.summary.competitors ?? []).find((c) => isCompetitor(c, row));
  if (contact?.last_failed) {
    return { kind: "failed" };
  }
  return contact?.last_sent_at ? { kind: "date", at: contact.last_sent_at } : { kind: "none" };
}

/** The sends that included this competitor, newest first as the log gives them. */
export function entriesFor(entries: readonly EmailLogEntry[], row: Pick<Row, "adherent_id" | "email">): EmailLogEntry[] {
  return entries.filter((entry) => (entry.recipients ?? []).some((r) => isCompetitor(r, row)));
}

/** « 24/10/2026 » for a server date. */
export function dayOf(at: string): string {
  const date = parseDate(at);
  return date ? formatDate(date) : at;
}
