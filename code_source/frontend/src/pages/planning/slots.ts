/* The Planning page's slots: placement on the week grid, table filters, the slot form and its checks
   (texts and rules of the former web/bureau/planning.html). */
import type { Schemas } from "../../lib/client";
import { plural } from "../../lib/text";

export type Slot = Schemas["PlanningSlot"];
export type SlotUpdate = Schemas["PlanningSlotUpdate"];

/** Columns of the week grid (the Excel grid has the same: exports/planning_excel.py). */
export const DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"] as const;
const FORM_DAYS = [...DAYS, "Dimanche"];

export const TYPES = [
  ["cours", "Cours / Loisir"],
  ["perfectionnement", "Perfectionnement"],
  ["compétition", "Compétition"],
  ["autonome", "Autonome"],
  ["découverte", "Découverte"],
  ["autre", "Autre"],
] as const;

// The grid shows 9:00 to 22:00, HOUR_PX pixels per hour
export const FIRST_HOUR = 9;
export const HOURS = Array.from({ length: 13 }, (_, i) => FIRST_HOUR + i);
export const HOUR_PX = 50;

/** "18:00 - 20:00", "18h30–20h", "17:00 18:00" → [18, 20]: the first two times, whatever separates them (same rule
    as parse_horaire in exports/planning_excel.py); null when unreadable or not increasing. */
export function parseHours(horaires: string): [number, number] | null {
  const times: number[] = [];
  for (const m of horaires.matchAll(/(\d{1,2})\s*[:h]\s*(\d{1,2})?/gi)) {
    const h = Number(m[1]);
    const min = Number(m[2] ?? 0);
    if (h <= 23 && min <= 59) {
      times.push(h + min / 60);
    }
  }
  const [start, end] = times;
  return start !== undefined && end !== undefined && end > start ? [start, end] : null;
}

/** Colour of a slot: from its type, or its name for old slots. */
export type Kind = "competition" | "perfectionnement" | "cours" | "autonome-bloc" | "autonome";

export function slotKind(slot: Pick<Slot, "type" | "groupe">): Kind {
  const t = slot.type.toLowerCase();
  const g = slot.groupe.toLowerCase();
  if (t.includes("comp") || g.includes("comp")) {
    return "competition";
  }
  if (t.includes("perf") || g.includes("perf")) {
    return "perfectionnement";
  }
  if (t.includes("autonome") || g.includes("autonome")) {
    return g.includes("bloc") ? "autonome-bloc" : "autonome";
  }
  return "cours";
}

/** A slot on the grid: position in its day column (pixels from 9:00, and a share of the width when slots overlap). */
export interface Placed {
  slot: Slot;
  top: number;
  height: number;
  lane: number;
  lanes: number;
}

/** Places a day's slots: overlapping slots side by side, each in the first free lane. */
export function layoutDay(slots: readonly Slot[]): Placed[] {
  const timed = slots
    .map((slot) => ({ slot, hours: parseHours(slot.horaires) }))
    .filter((s): s is { slot: Slot; hours: [number, number] } => s.hours !== null)
    .sort((a, b) => a.hours[0] - b.hours[0] || b.hours[1] - b.hours[0] - (a.hours[1] - a.hours[0]));
  const laneEnds: number[] = [];
  const placed = timed.map(({ slot, hours: [start, end] }) => {
    let lane = laneEnds.findIndex((laneEnd) => laneEnd <= start + 0.05);
    if (lane === -1) {
      lane = laneEnds.length;
    }
    laneEnds[lane] = end;
    return { slot, top: Math.max(0, (start - FIRST_HOUR) * HOUR_PX), height: Math.max(28, (end - start) * HOUR_PX - 4), lane };
  });
  const lanes = Math.max(1, laneEnds.length);
  return placed.map((p) => ({ ...p, lanes }));
}

/** The grid's columns. A slot of several days ("Lundi / Jeudi") or of Sunday has no column. */
export function week(slots: readonly Slot[]): { day: (typeof DAYS)[number]; placed: Placed[] }[] {
  return DAYS.map((day) => ({ day, placed: layoutDay(slots.filter((s) => s.jour.toLowerCase() === day.toLowerCase())) }));
}

// Table filters
export const KINDS = [
  ["all", "Tous"],
  ["cours", "Cours"],
  ["perfectionnement", "Perfectionnement"],
  ["compétition", "Compétition"],
  ["autonome", "Autonome"],
] as const;
export type KindFilter = (typeof KINDS)[number][0];

function matchesKind(slot: Slot, kind: KindFilter): boolean {
  const t = slot.type.toLowerCase();
  const g = slot.groupe.toLowerCase();
  if (kind === "cours") {
    return t.includes("cours") || g.includes("loisir");
  }
  if (kind === "perfectionnement") {
    return t.includes("perf") || g.includes("perf");
  }
  if (kind === "compétition") {
    return t.includes("comp") || g.includes("comp");
  }
  if (kind === "autonome") {
    return t.includes("autonome") || g.includes("autonome");
  }
  return true;
}

/** Slots of the kind whose name, day, hours, type, age category, coaches or tariffs contain the search. */
export function filterSlots(slots: readonly Slot[], search: string, kind: KindFilter): Slot[] {
  const q = search.trim().toLowerCase();
  return slots.filter((s) => {
    if (!matchesKind(s, kind)) {
      return false;
    }
    if (!q) {
      return true;
    }
    const text = [s.groupe, s.jour, s.horaires, s.type, s.categorie_age, s.encadrants.join(" "), s.helloasso_tarifs.join(" ")];
    return text.join(" ").toLowerCase().includes(q);
  });
}

export function countLabel(count: number): string {
  return `${count} créneau${plural(count, "x")} configuré${plural(count)}`;
}

/** The slot form: coaches typed as one text, separated by commas. */
export interface SlotDraft extends Omit<Required<SlotUpdate>, "encadrants"> {
  encadrants: string;
}

export function draftOf(slot?: Slot): SlotDraft {
  if (!slot) {
    return {
      id: 0,
      groupe: "",
      jour: "Lundi",
      horaires: "18:00 - 20:00",
      type: "cours",
      categorie_age: "",
      encadrants: "",
      helloasso_tarifs: [],
      whatsapp_link: "",
      naissance_min: "",
      naissance_max: "",
      seance_autonome: false,
    };
  }
  return { ...slot, helloasso_tarifs: [...slot.helloasso_tarifs], encadrants: slot.encadrants.join(", ") };
}

export function updateOf(draft: SlotDraft): SlotUpdate {
  return {
    ...draft,
    encadrants: draft.encadrants
      .split(",")
      .map((e) => e.trim())
      .filter(Boolean),
  };
}

/** The form's days: the week, plus the slot's own when it is not one of them ("Lundi / Jeudi" stays as it is). */
export function dayOptions(current: string): string[] {
  return current && !FORM_DAYS.includes(current) ? [...FORM_DAYS, current] : FORM_DAYS;
}

/** The form's types, plus the slot's own when it is not one of them. */
export function typeOptions(current: string): [string, string][] {
  const known: [string, string][] = TYPES.map(([value, label]) => [value, label]);
  return current && !known.some(([value]) => value === current) ? [...known, [current, current]] : known;
}

/** The tariffs to tick: the season's, plus those the slot is already linked to (kept when it is saved). */
export function tarifOptions(season: readonly string[], linked: readonly string[]): string[] {
  return [...season, ...linked.filter((t) => !season.includes(t))];
}

/** Why the slot cannot be saved, or null. */
export function slotError(draft: SlotDraft): string | null {
  if (!draft.groupe.trim()) {
    return "⚠️ Le nom du groupe est obligatoire.";
  }
  if (!draft.horaires.trim()) {
    return "⚠️ Les horaires sont obligatoires.";
  }
  if (!parseHours(draft.horaires)) {
    return "⚠️ Horaires illisibles : écrivez-les comme « 18:00 - 20:00 ».";
  }
  return null;
}

// ---------------------------------------------------------------- Calendar file (.ics)

const ICS_DAYS: Record<string, string> = {
  lundi: "MO",
  mardi: "TU",
  mercredi: "WE",
  jeudi: "TH",
  vendredi: "FR",
  samedi: "SA",
  dimanche: "SU",
};
const WEEKDAYS = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];

/** Text value of an iCalendar property (RFC 5545 § 3.3.11). */
function icsText(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/;/g, "\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

const two = (n: number): string => String(n).padStart(2, "0");
const icsDay = (d: Date): string => `${d.getFullYear()}${two(d.getMonth() + 1)}${two(d.getDate())}`;
const icsTime = (hours: number): string => {
  const minutes = Math.round(hours * 60);
  return `${two(Math.floor(minutes / 60))}${two(minutes % 60)}00`;
};

/** "Lundi / Jeudi" → ["MO", "TH"]; empty when no day is named. */
export function icsDays(jour: string): string[] {
  return [...new Set((jour.toLowerCase().match(/[a-z]+/g) ?? []).map((word) => ICS_DAYS[word]).filter((d): d is string => !!d))];
}

/**
 * The slots as weekly events, from 1 September of the season of `now` to 30 June, at their Paris times (Google
 * Calendar import). Slots without a readable day or hours are left out and counted.
 */
export function planningIcs(slots: readonly Slot[], now: Date): { ics: string; skipped: number } {
  const seasonYear = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
  const stamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d+/, "");
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//ALJ Escalade//Planning//FR",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:ALJ Escalade — Planning",
    "X-WR-TIMEZONE:Europe/Paris",
  ];
  let skipped = 0;
  for (const s of slots) {
    const days = icsDays(s.jour);
    const hours = parseHours(s.horaires);
    if (!days.length || !hours) {
      skipped++;
      continue;
    }
    // The first event is the first of these days from 1 September (an extra one otherwise, RFC 5545 § 3.8.5.3)
    const first = new Date(seasonYear, 8, 1);
    while (!days.includes(WEEKDAYS[first.getDay()]!)) {
      first.setDate(first.getDate() + 1);
    }
    lines.push(
      "BEGIN:VEVENT",
      `UID:alj-slot-${s.id}@alj-escalade.fr`,
      `DTSTAMP:${stamp}`,
      `SUMMARY:${icsText(`ALJ Escalade — ${s.groupe}`)}`,
      `DESCRIPTION:${icsText([s.type, s.encadrants.join(", ")].filter(Boolean).join(" · "))}`,
      `DTSTART;TZID=Europe/Paris:${icsDay(first)}T${icsTime(hours[0])}`,
      `DTEND;TZID=Europe/Paris:${icsDay(first)}T${icsTime(hours[1])}`,
      `RRULE:FREQ=WEEKLY;BYDAY=${days.join(",")};UNTIL=${seasonYear + 1}0630T215959Z`,
      "END:VEVENT",
    );
  }
  lines.push("END:VCALENDAR");
  return { ics: lines.join("\r\n"), skipped };
}
