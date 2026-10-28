/* The Compétitions calendar: the month's weeks, the competitions laid out as bars over them (several days → one bar,
   overlapping ones on separate lanes) and the month's list for phones. Dates are local "YYYY-MM-DD" strings, compared
   as text; never toISOString(), which is UTC and shifts the day in the evening. */
import type { BadgeColor } from "../../../components/ui/palette";
import { discipline, DISCIPLINE_COLOR, disciplineColor, isArchived, todayIso, type Competition } from "../competitions";

/** A month; `month` from 0 (January) to 11, as in Date. */
export interface YearMonth {
  year: number;
  month: number;
}

export interface CalendarDay {
  dateIso: string;
  dayNumber: number;
  inMonth: boolean;
  isToday: boolean;
}

/** A competition's bar on one week row: columns from 0 (Monday), lanes from 0 (top). */
export interface CalendarBar {
  competition: Competition;
  startCol: number;
  span: number;
  lane: number;
  /** It started in an earlier week, it goes on in the next one. */
  continuesBefore: boolean;
  continuesAfter: boolean;
}

/** The date `days` after `dateIso` (before when negative). Date rolls over months and years. */
export function addDays(dateIso: string, days: number): string {
  const [year, month, day] = dateIso.split("-").map(Number) as [number, number, number];
  return todayIso(new Date(year, month - 1, day + days));
}

/** Days from `from` to `to` (both "YYYY-MM-DD"); UTC here only to count days without daylight saving changes. */
function daysBetween(from: string, to: string): number {
  const utc = (iso: string) => {
    const [year, month, day] = iso.split("-").map(Number) as [number, number, number];
    return Date.UTC(year, month - 1, day);
  };
  return Math.round((utc(to) - utc(from)) / 86_400_000);
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}/;

/** First and last day of a competition: no end date, or one before the start, means a single day; null without a
    readable start date (it has no place on the calendar). */
export function competitionDays(c: Competition): [string, string] | null {
  const start = c.date_competition ?? "";
  if (!ISO_DAY.test(start)) {
    return null;
  }
  const first = start.slice(0, 10);
  const end = (c.date_fin ?? "").slice(0, 10);
  return [first, ISO_DAY.test(end) && end > first ? end : first];
}

export function shiftMonth({ year, month }: YearMonth, delta: number): YearMonth {
  const date = new Date(year, month + delta, 1);
  return { year: date.getFullYear(), month: date.getMonth() };
}

/** The month shown first: the selected competition's, otherwise today's. */
export function initialMonth(selected: Competition | undefined, today: string): YearMonth {
  const [day] = (selected && competitionDays(selected)) || [today];
  const [year, month] = day.split("-").map(Number) as [number, number];
  return { year, month: month - 1 };
}

/** The weeks showing the month, Monday first, completed with the days of the months around it. */
export function monthWeeks({ year, month }: YearMonth, today: string): CalendarDay[][] {
  const first = todayIso(new Date(year, month, 1));
  const mondayOffset = (new Date(year, month, 1).getDay() + 6) % 7;
  const dayCount = new Date(year, month + 1, 0).getDate();
  const weekCount = Math.ceil((mondayOffset + dayCount) / 7);
  const prefix = first.slice(0, 7);
  return Array.from({ length: weekCount }, (_, week) =>
    Array.from({ length: 7 }, (_, weekday) => {
      const dateIso = addDays(first, week * 7 + weekday - mondayOffset);
      return { dateIso, dayNumber: Number(dateIso.slice(8)), inMonth: dateIso.startsWith(prefix), isToday: dateIso === today };
    }),
  );
}

/** The competitions overlapping the 7 days from `weekStart`, as bars: by start, longer first, each on the first lane
    free on all its days. `lanes`: how many lanes the row needs. */
export function layoutWeek(competitions: readonly Competition[], weekStart: string): { bars: CalendarBar[]; lanes: number } {
  const weekEnd = addDays(weekStart, 6);
  const shown = competitions
    .map((competition) => ({ competition, days: competitionDays(competition) }))
    .filter((c): c is { competition: Competition; days: [string, string] } => !!c.days && c.days[0] <= weekEnd && c.days[1] >= weekStart)
    .sort(
      (a, b) =>
        a.days[0].localeCompare(b.days[0]) ||
        b.days[1].localeCompare(a.days[1]) ||
        (a.competition.nom ?? "").localeCompare(b.competition.nom ?? ""),
    );
  // Per lane, the last column taken
  const laneEnds: number[] = [];
  const bars = shown.map(({ competition, days: [start, end] }) => {
    const startCol = Math.max(0, daysBetween(weekStart, start));
    const endCol = Math.min(6, daysBetween(weekStart, end));
    let lane = laneEnds.findIndex((taken) => taken < startCol);
    if (lane === -1) {
      lane = laneEnds.length;
    }
    laneEnds[lane] = endCol;
    return { competition, startCol, span: endCol - startCol + 1, lane, continuesBefore: start < weekStart, continuesAfter: end > weekEnd };
  });
  return { bars, lanes: laneEnds.length };
}

/** The month's competitions (any of their days in it), by start date then name: the calendar on phones. */
export function monthAgenda(competitions: readonly Competition[], { year, month }: YearMonth): Competition[] {
  const first = todayIso(new Date(year, month, 1));
  const last = todayIso(new Date(year, month + 1, 0));
  return competitions
    .map((competition) => ({ competition, days: competitionDays(competition) }))
    .filter((c): c is { competition: Competition; days: [string, string] } => !!c.days && c.days[0] <= last && c.days[1] >= first)
    .sort((a, b) => a.days[0].localeCompare(b.days[0]) || (a.competition.nom ?? "").localeCompare(b.competition.nom ?? ""))
    .map((c) => c.competition);
}

/** A bar's colour: its discipline's (as its badge); slate without one (blue is « difficulté ») and once archived. */
export function calendarColor(c: Competition): BadgeColor {
  const name = discipline(c).toLowerCase();
  return !isArchived(c) && name ? disciplineColor(name) : "slate";
}

/** The legend: the known disciplines, then the others. */
export const LEGEND: { label: string; color: BadgeColor }[] = [
  ...Object.entries(DISCIPLINE_COLOR).map(([name, color]) => ({ label: name.charAt(0).toUpperCase() + name.slice(1), color })),
  { label: "Autre / non précisé", color: "slate" },
];

const MONTH = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" });
const WEEKDAY = new Intl.DateTimeFormat("fr-FR", { weekday: "short" });
const AGENDA_DAY = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "short" });

/** A "YYYY-MM-DD" day as a local Date (for Intl). */
function localDate(dateIso: string): Date {
  const [year, month, day] = dateIso.split("-").map(Number) as [number, number, number];
  return new Date(year, month - 1, day);
}

/** « Novembre 2026 ». */
export function monthTitle({ year, month }: YearMonth): string {
  const text = MONTH.format(new Date(year, month, 1));
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** « lun. » … « dim. », the columns' headers (2024-01-01 was a Monday). */
export const WEEKDAYS = Array.from({ length: 7 }, (_, i) => WEEKDAY.format(new Date(2024, 0, 1 + i)));

/** « sam. 15 nov. », « sam. 15 nov. – dim. 16 nov. » (a competition without a readable date: « sans date »). */
export function agendaDays(c: Competition): string {
  const days = competitionDays(c);
  if (!days) {
    return "sans date";
  }
  const [start, end] = days.map((d) => AGENDA_DAY.format(localDate(d)));
  return start === end ? start! : `${start} – ${end}`;
}
