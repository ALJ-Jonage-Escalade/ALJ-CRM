/* Member list of Adhérents: slot / tariff filters, search, status, sorting and CSV export (port of the former
   web/shared/alj-filters.js and alj-members.js).
   The members come formatted by the server (GET /api/members, domain/members/view.py). */
import type { BadgeColor } from "../../components/ui/palette";
import { localStorageOrNone } from "../../lib/localStorage";
import type { Cell } from "../../lib/csv";
import type { Schemas } from "../../lib/client";
import { emergencyContactsOf } from "../../lib/emergencyContacts";
import { formatDayText } from "../../lib/format";
import { PASSPORT_COLOURS } from "../../lib/passports";
import { SEX_LABELS } from "../../lib/sex";
import { normKey, plural } from "../../lib/text";
import type { MemberStatus } from "../../services/members";

export type Member = Schemas["Member"];
export type Creneau = Schemas["Creneau"];
export type MemberList = Schemas["MemberList"];

/** Indique si un adhérent appartient à un groupe ou tarif compétition. */
export function isCompetitor(member: Member): boolean {
  const group = normKey(member.creneau_groupe);
  const tarif = normKey(member.tarif_name);
  return group.includes("competition") || tarif.includes("competition");
}

// ---------------------------------------------------------------- Slot groups and tariffs

/** A line of the slot filter: a section title, a sub-section (birth years) or a slot group with its tariffs. */
export type CreneauItem =
  { kind: "section" | "sub"; label: string; raw: string } | { kind: "group"; label: string; raw: string; tarifs: string[] };

const ACCENTS: Record<string, string> = { e: "[eèéêë]", a: "[aàâä]", i: "[iîï]", o: "[oôö]", u: "[uùûü]", c: "[cç]", y: "[yÿ]" };

function accentPattern(word: string): string {
  return [...word].map((ch) => ACCENTS[ch] ?? ch).join("");
}

/** The group name without its section keyword: "Enfants 2015-2016 mercredi" -> "mercredi" (with drop: the years). */
export function shortenGroupLabel(name: string, keyword: string, drop: string[] = []): string {
  const parts = name.split(new RegExp(accentPattern(keyword), "i"));
  let rest = parts.length > 1 ? parts.reduce((a, b) => (b.length > a.length ? b : a)) : name;
  for (const pattern of drop) {
    rest = rest.replace(new RegExp(pattern, "ig"), "");
  }
  rest = rest.replace(/\s{2,}/g, " ").replace(/^[\s–—-]+|[\s–—-]+$/g, "");
  if (rest.startsWith("(") && rest.endsWith(")")) {
    rest = rest.slice(1, -1).trim();
  }
  return rest || name;
}

/** Waiting lists are left out of the list until checked. */
export function isWaiting(raw: string, label: string = raw): boolean {
  return normKey(raw).includes("attente") || normKey(label).includes("attente");
}

const SECTIONS = ["Collège", "Enfants", "Perfectionnement", "Compétition"] as const;
type Section = (typeof SECTIONS)[number];

/** The keyword that puts a slot group in its section, checked in this order (« Compétition » before the others). */
const SECTION_KEYWORDS: readonly [string, Section][] = [
  ["competition", "Compétition"],
  ["college", "Collège"],
  ["enfants", "Enfants"],
  ["perfectionnement", "Perfectionnement"],
];

/** Lines of the slot filter: groups outside the sections first, then each section (Enfants by birth years). */
export function creneauItems(creneaux: readonly Creneau[]): CreneauItem[] {
  const lists: Record<Exclude<Section, "Enfants">, [string, string][]> = {
    Collège: [],
    Perfectionnement: [],
    Compétition: [],
  };
  const children: Record<string, [string, string][]> = {};
  const others: [string, string][] = [];

  for (const creneau of creneaux) {
    const name = creneau.groupe;
    const key = normKey(name);
    const [keyword, section] = SECTION_KEYWORDS.find(([word]) => key.includes(word)) ?? [];
    if (!keyword || !section) {
      others.push([name, name]);
    } else if (section === "Enfants") {
      const years = key.match(/20\d\d\s*-\s*20\d\d/);
      const ageBand = years ? years[0].replace(/\s/g, "") : "Autres tranches";
      (children[ageBand] ??= []).push([name, shortenGroupLabel(name, keyword, ["20\\d\\d\\s*-\\s*20\\d\\d"])]);
    } else {
      lists[section].push([name, shortenGroupLabel(name, keyword)]);
    }
  }

  const tarifsOf = new Map(creneaux.map((c) => [c.groupe, c.tarifs]));
  const byName = (a: [string, string], b: [string, string]) => a[0].localeCompare(b[0], "fr");
  const groups = (entries: [string, string][]): CreneauItem[] =>
    entries.sort(byName).map(([raw, label]) => ({ kind: "group", label, raw, tarifs: tarifsOf.get(raw) ?? [] }));

  const items: CreneauItem[] = groups(others);
  for (const section of SECTIONS) {
    if (section === "Enfants") {
      const subs = Object.keys(children).sort((left, right) => left.localeCompare(right, "fr"));
      if (!subs.length) {
        continue;
      }
      items.push({ kind: "section", label: section, raw: section });
      for (const sub of subs) {
        items.push({ kind: "sub", label: sub, raw: sub }, ...groups(children[sub]!));
      }
    } else if (lists[section].length) {
      items.push({ kind: "section", label: section, raw: section }, ...groups(lists[section]));
    }
  }
  return items;
}

/** Members of each line of the filter: by slot group, and the tariffs no slot covers ("Autres tarifs"). */
export interface TarifCounts {
  groups: Record<string, number>;
  others: Record<string, number>;
}

export function tarifCounts(members: readonly Pick<Member, "tarif_name">[], items: readonly CreneauItem[]): TarifCounts {
  const covered = new Set<string>();
  for (const it of items) {
    if (it.kind === "group") {
      for (const t of it.tarifs) {
        covered.add(normKey(t));
      }
    }
  }
  const byTarif: Record<string, number> = {};
  const others: Record<string, number> = {};
  for (const m of members) {
    const k = normKey(m.tarif_name);
    if (!k) {
      continue;
    }
    byTarif[k] = (byTarif[k] ?? 0) + 1;
    if (!covered.has(k)) {
      others[m.tarif_name] = (others[m.tarif_name] ?? 0) + 1;
    }
  }
  const groups: Record<string, number> = {};
  for (const it of items) {
    if (it.kind === "group") {
      groups[it.raw] = it.tarifs.reduce((sum, t) => sum + (byTarif[normKey(t)] ?? 0), 0);
    }
  }
  return { groups, others };
}

// ---------------------------------------------------------------- Filters

/** Filters of the list. groups / others: checked or not, by group name / "other:<tariff>"; missing = default. */
export interface Filters {
  season: string;
  status: string;
  search: string;
  groups: Record<string, boolean>;
  others: Record<string, boolean>;
}

export const OTHER_PREFIX = "other:";

export function emptyFilters(): Filters {
  return { season: "", status: "", search: "", groups: {}, others: {} };
}

export function groupChecked(filters: Filters, it: CreneauItem): boolean {
  return filters.groups[it.raw] ?? !isWaiting(it.raw, it.label);
}

export function otherChecked(filters: Filters, tarif: string): boolean {
  return filters.others[OTHER_PREFIX + tarif] ?? !isWaiting(tarif);
}

/** Normalized tariffs of the checked lines. */
export function allowedTarifs(items: readonly CreneauItem[], counts: TarifCounts, filters: Filters): Set<string> {
  const allowed = new Set<string>();
  for (const it of items) {
    if (it.kind === "group" && groupChecked(filters, it)) {
      for (const t of it.tarifs) {
        allowed.add(normKey(t));
      }
    }
  }
  for (const t of Object.keys(counts.others)) {
    if (otherChecked(filters, t)) {
      allowed.add(normKey(t));
    }
  }
  return allowed;
}

/** Every line checked (true) or none (false). */
export function checkAll(filters: Filters, items: readonly CreneauItem[], counts: TarifCounts, on: boolean): Filters {
  const groups = { ...filters.groups };
  const others = { ...filters.others };
  for (const it of items) {
    if (it.kind === "group") {
      groups[it.raw] = on;
    }
  }
  for (const t of Object.keys(counts.others)) {
    others[OTHER_PREFIX + t] = on;
  }
  return { ...filters, groups, others };
}

const digits = (s: string) => s.replace(/\D/g, "");

/** What the search and the filters read of a member (the directory keeps fewer fields: no comment). */
export type FilteredMember = Pick<
  Member,
  "last_name" | "first_name" | "tarif_name" | "licence_ffme" | "email_primary" | "phone" | "city" | "status_norm"
> &
  Partial<Pick<Member, "commentaires_correctif">>;

/** The search finds names (both orders), tariff, licence, e-mail, phone (4 digits at least, any spacing), city, comment. */
export function matchesSearch(member: FilteredMember, search: string): boolean {
  const q = normKey(search);
  if (!q) {
    return true;
  }
  const qDigits = digits(q);
  if (qDigits.length >= 4 && digits(member.phone).includes(qDigits)) {
    return true;
  }
  return [
    member.last_name,
    member.first_name,
    `${member.first_name} ${member.last_name}`,
    `${member.last_name} ${member.first_name}`,
    member.tarif_name,
    member.licence_ffme,
    member.email_primary,
    member.phone,
    member.city,
    member.commentaires_correctif,
  ].some((field) => field && normKey(field).includes(q));
}

/** A member without a tariff is always listed (as on the former page). */
export function filterMembers<M extends FilteredMember>(members: readonly M[], filters: Filters, allowed: Set<string>): M[] {
  return members.filter((m) => {
    const k = normKey(m.tarif_name);
    if (k && !allowed.has(k)) {
      return false;
    }
    if (filters.status && m.status_norm !== filters.status) {
      return false;
    }
    return matchesSearch(m, filters.search);
  });
}

// ---------------------------------------------------------------- Display

/** The membership statuses, in display order (the contract's status union: a new server status breaks the build). */
export const STATUSES = ["Validé", "Traité", "Terminé", "En cours", "Annulé"] as const satisfies readonly MemberStatus[];

/** Status chips: « Tous » then the statuses some member has, with their counts. */
export function statusChips(members: readonly Pick<Member, "status_norm">[]): { value: string; label: string; count: number }[] {
  const chips = [{ value: "", label: "Tous", count: members.length }];
  for (const st of STATUSES) {
    const count = members.filter((m) => m.status_norm === st).length;
    if (count) {
      chips.push({ value: st, label: st, count });
    }
  }
  return chips;
}

const STATUS_COLOR: Record<string, BadgeColor> = {
  Validé: "green",
  Traité: "blue",
  Terminé: "violet",
  "En cours": "amber",
  Annulé: "red",
};

/** Colour of a status badge. */
export const statusColor = (status: string): BadgeColor => STATUS_COLOR[status] ?? "slate";

/** A yes/no column of the membership file read as a flag: « oui », « x », « true » or « 1 ». */
export const isYes = (value: string): boolean => ["oui", "x", "true", "1"].includes(value.trim().toLowerCase());

export interface Diplome {
  type: "badge_rouge" | "autonomie_bloc" | "passeport_orange";
  label: string;
  icon: string;
}

/** Badges of the Diplôme column: red badge, bouldering autonomy, orange passport. */
export function diplomes(member: Pick<Member, "badge_rouge" | "autonomie_bloc" | "raw_passports" | "passeport_orange">): Diplome[] {
  const items: Diplome[] = [];
  if (isYes(member.badge_rouge)) {
    items.push({ type: "badge_rouge", label: "Badge rouge diff", icon: "🔴" });
  }
  if (isYes(member.autonomie_bloc)) {
    items.push({ type: "autonomie_bloc", label: "Autonomie bloc", icon: "🧗" });
  }
  const passports = `${member.raw_passports} ${member.passeport_orange}`.toLowerCase();
  if (passports.includes("orange") || member.passeport_orange.toLowerCase() === "oui") {
    items.push({ type: "passeport_orange", label: "Passeport orange", icon: PASSPORT_COLOURS.orange });
  }
  return items;
}

/** Sort weight of the Diplôme column: red badge 4, autonomy 2, orange passport 1. */
export function diplomeWeight(member: Member): number {
  const weights = { badge_rouge: 4, autonomie_bloc: 2, passeport_orange: 1 };
  return diplomes(member).reduce((sum, d) => sum + weights[d.type], 0);
}

/** Milliseconds of an ISO or French date, 0 when empty or unreadable (sorted first). */
export function dateValue(text: string): number {
  const str = text.trim();
  if (!str) {
    return 0;
  }
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(str);
  if (iso) {
    const t = Date.parse(str.length > 10 ? str : `${str}T00:00:00`);
    return Number.isNaN(t) ? new Date(+iso[1]!, +iso[2]! - 1, +iso[3]!).getTime() : t;
  }
  const fr = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})/.exec(str);
  if (fr) {
    return new Date(+fr[3]!, +fr[2]! - 1, +fr[1]!).getTime();
  }
  const t = Date.parse(str);
  return Number.isNaN(t) ? 0 : t;
}

/** Text comparison of the columns: French, case and accents ignored, numbers in order ("U9" before "U11"). */
export const collator = new Intl.Collator("fr", { sensitivity: "base", numeric: true });

/** Query of Adhérents opening the member's record on its season: ?id=<user_id>&saison=…&achat=<purchase_id>
    (id and saison are the links of the former page, which still open the member; achat picks the membership when a
    member has several in a season). ?ajout=1 opens the add form. */
export type RecordQuery = { id: string; saison: string; achat?: string } | { ajout: "1" };

export function recordQuery(member: Member): RecordQuery {
  return { id: String(member.user_id), saison: member.season_name, achat: String(member.purchase_id) };
}

/** The member a record query names, among the members of its season (undefined: not, or not yet, loaded). */
export function recordMember(members: readonly Member[], id: string, achat?: string): Member | undefined {
  const mine = members.filter((m) => String(m.user_id) === id);
  return mine.find((m) => String(m.purchase_id) === achat) ?? mine[0];
}

export function countSummary(shown: number, total: number, season: string): string {
  return `${shown} adhérent${plural(shown)} affiché${plural(shown)} sur ${total} (saison ${season})`;
}

// ---------------------------------------------------------------- CSV export

const CSV_HEADERS_BEFORE_CONTACTS = [
  "Nom",
  "Prénom",
  "Date de naissance",
  "Âge",
  "Sexe",
  "Catégorie",
  "Créneau",
  "Tarif",
  "Montant (€)",
  "Statut",
  "N° Licence FFME",
  "E-mail principal",
  "E-mail secondaire",
  "Téléphone",
  "Adresse",
  "Code postal",
  "Ville",
];
const CSV_HEADERS_AFTER_CONTACTS = ["Payeur", "E-mail payeur", "Réf Commande", "Date commande"];

/** Rows of the CSV export of the list shown (same columns as the former page), for lib/csv.ts. */
export function csvRows(members: readonly Member[]): Cell[][] {
  const contactsOf = members.map((m) => emergencyContactsOf(m));
  // Two pairs of columns at least, as always, and as many as the longest list so that no contact is lost
  const contactColumns = Array.from({ length: Math.max(2, ...contactsOf.map((contacts) => contacts.length)) }, (_, position) => position);
  return [
    [
      ...CSV_HEADERS_BEFORE_CONTACTS,
      ...contactColumns.flatMap((position) => [`Urgence ${position + 1} - Nom`, `Urgence ${position + 1} - Tél`]),
      ...CSV_HEADERS_AFTER_CONTACTS,
    ],
    ...members.map((m, memberIndex) => [
      m.last_name,
      m.first_name,
      formatDayText(m.birth_date),
      m.age,
      m.sex ? SEX_LABELS[m.sex] : "",
      m.categorie,
      m.creneau_groupe,
      m.tarif_name,
      m.amount,
      m.status_norm,
      m.licence_ffme,
      m.email_primary,
      m.email_secondary,
      m.phone,
      m.address,
      m.zip_code,
      m.city,
      ...contactColumns.flatMap((position) => {
        const contact = contactsOf[memberIndex]?.[position];
        return [contact?.name ?? "", contact?.phone ?? ""];
      }),
      m.payer,
      m.payer_email,
      m.order_ref,
      formatDayText(m.order_date),
    ]),
  ];
}

export function csvName(season: string): string {
  return `adherents_${(season || "saison").replace(/[^\w-]/g, "_")}.csv`;
}

// ---------------------------------------------------------------- Saved filters

/** Same key and shape as the former page (web/shared/alj-filters.js): the filters of earlier visits are kept. */
export const ADHERENTS_FILTERS_STORAGE = "alj_bureau_adherents_filters";

/** The filters of the last visit on this browser (key: another page's filters). The search is not kept: it often
    holds a member's name. */
export function loadFilters(
  storage: Pick<Storage, "getItem"> | undefined = localStorageOrNone(),
  key = ADHERENTS_FILTERS_STORAGE,
): Filters {
  const filters = emptyFilters();
  try {
    const saved: unknown = JSON.parse(storage?.getItem(key) || "{}");
    if (!saved || typeof saved !== "object") {
      return filters;
    }
    const { season, status, groups, others } = saved as Record<string, unknown>;
    if (typeof season === "string") {
      filters.season = season;
    }
    if (typeof status === "string") {
      filters.status = status;
    }
    filters.groups = booleans(groups);
    filters.others = booleans(others);
  } catch {
    // unreadable or blocked storage: default filters
  }
  return filters;
}

function booleans(value: unknown): Record<string, boolean> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.fromEntries(Object.entries(value).filter((e): e is [string, boolean] => typeof e[1] === "boolean"));
}

export function saveFilters(
  filters: Filters,
  storage: Pick<Storage, "setItem"> | undefined = localStorageOrNone(),
  key = ADHERENTS_FILTERS_STORAGE,
): void {
  try {
    storage?.setItem(key, JSON.stringify({ ...filters, search: "" }));
  } catch {
    // blocked storage: the filters last for this visit only
  }
}

// ---------------------------------------------------------------- Record panel

export const ADHERENTS_PANEL_STORAGE = "alj_bureau_adherents_panel";

/** Whether the record panel was left open on this browser (open by default). */
export function loadPanelOpen(storage: Pick<Storage, "getItem"> | undefined = localStorageOrNone()): boolean {
  try {
    return storage?.getItem(ADHERENTS_PANEL_STORAGE) !== "closed";
  } catch {
    return true; // blocked storage: open
  }
}

export function savePanelOpen(open: boolean, storage: Pick<Storage, "setItem"> | undefined = localStorageOrNone()): void {
  try {
    storage?.setItem(ADHERENTS_PANEL_STORAGE, open ? "open" : "closed");
  } catch {
    // blocked storage: the choice lasts for this visit only
  }
}
