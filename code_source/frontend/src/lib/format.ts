/* Dates, times and amounts written the French way, shared by every page. The Intl formatters are built once here
   rather than in each component. */

const DATE = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short" });
const DATE_TIME = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });
const DATE_TIME_SECONDS = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "medium" });
const TIME_SECONDS = new Intl.DateTimeFormat("fr-FR", { timeStyle: "medium" });
const EUROS = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

/** « 24/10/2026 ». */
export function formatDate(date: Date): string {
  return DATE.format(date);
}

/** « 24/10/2026 14:05 ». */
export function formatDateTime(date: Date): string {
  return DATE_TIME.format(date);
}

/** « 24/10/2026 14:05:09 ». */
export function formatDateTimeSeconds(date: Date): string {
  return DATE_TIME_SECONDS.format(date);
}

/** « 14:05:09 ». */
export function formatTime(date: Date): string {
  return TIME_SECONDS.format(date);
}

/** The date in a server string (ISO or anything `Date` reads), or null when there is none. */
export function parseDate(text: string | null | undefined): Date | null {
  if (!text) {
    return null;
  }
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** « 12,50 € »; missing amounts count as zero. */
export function formatEuros(amount: number | null | undefined): string {
  return EUROS.format(Number(amount ?? 0));
}

/** A day written as text, ISO (2026-09-01, with or without time) or French (1/9/2026), as « 01/09/2026 »; anything
    else as is. Read from the text, not through `Date`, so the time zone never shifts the day. */
export function formatDayText(text: string): string {
  const str = text.trim();
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(str);
  if (iso) {
    return `${iso[3]}/${iso[2]}/${iso[1]}`;
  }
  const fr = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})/.exec(str);
  if (fr) {
    return `${fr[1]!.padStart(2, "0")}/${fr[2]!.padStart(2, "0")}/${fr[3]}`;
  }
  return str;
}
