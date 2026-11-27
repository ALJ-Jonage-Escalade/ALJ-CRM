/* Competitions screen: the competitions, their participants and payment status, and what coaches change on them (the
   former pages web/competitions.html and web/bureau/competitions.html, merged). The server checks every change. */
import type { BadgeColor } from "../../components/ui/palette";
import { CATEGORY_ORDER, categoryAndSexLabel } from "../../lib/category";
import type { Cell } from "../../lib/csv";
import type { ApiRead, Schemas } from "../../lib/client";
import { emergencyContactsOf, type EmergencyContactRow, type EmergencyContactSource } from "../../lib/emergencyContacts";
import { formatDayText } from "../../lib/format";
import type { Sex } from "../../lib/sex";
import { normKey, plural } from "../../lib/text";
import { ARCHIVED } from "../../services/competitions";
import type { MemberStatus } from "../../services/members";

export type Competition = Schemas["Competition"];
export type Participant = Schemas["CompetitionParticipant"];
export type CompetitorContact = Schemas["CompetitorContact"];
/** A competitor entry as found on a device: copies saved before the list existed have no `emergency_contacts`. */
export type SavedCompetitorContact = Omit<CompetitorContact, "emergency_contacts"> & EmergencyContactSource;
export type Coach = Schemas["Coach"];
/** What the screen keeps of the member directory (GET /api/competition-members limited to COMPETITOR_STATUSES, online only): the current tariff and
    slot group (contact dialog), the names, licence and e-mail to add one or write to them. */
export type MemberSlot = Pick<
  Schemas["CompetitionMember"],
  "id" | "nom" | "prenom" | "licence_ffme" | "email" | "email_secondaire" | "tarif" | "creneau_groupe"
>;

/** Membership statuses of the members offered as competitors (« Terminé »: FFME licence confirmed), sent as
    ?status= to GET /api/competition-members and POST …/load-group. The member list fetched with it also gives the
    participants their tariff and group: a licensed competitor never goes back to another status. */
export const COMPETITOR_STATUSES: readonly MemberStatus[] = ["Terminé"];
/** « Terminé » (or « Terminé » ou « Validé »…), for the coach-facing texts. */
export const competitorStatusesLabel = COMPETITOR_STATUSES.map((status) => `« ${status} »`).join(" ou ");

/** GET /api/competition-members limited to COMPETITOR_STATUSES. */
export function competitionMembersRead(): ApiRead<"/api/competition-members"> {
  return { path: "/api/competition-members", query: { status: [...COMPETITOR_STATUSES] } };
}

/** The answer of GET /api/competition-members reduced to the fields above (phones and emergency contacts stay on the server). */
export function toMemberSlots(answer: readonly Schemas["CompetitionMember"][]): MemberSlot[] {
  return answer.map((m) => ({
    id: m.id,
    nom: m.nom ?? "",
    prenom: m.prenom ?? "",
    licence_ffme: m.licence_ffme || m.num_licence || "",
    email: m.email ?? "",
    email_secondaire: m.email_secondaire ?? "",
    tarif: m.tarif ?? "",
    creneau_groupe: m.creneau_groupe ?? "",
  }));
}

export const isArchived = (competition: Competition): boolean => competition.statut === ARCHIVED;

/** Today as YYYY-MM-DD, local time. */
export function todayIso(date: Date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** Over: ended before today (undated ones never are). */
export const isPast = (competition: Competition, today: string): boolean =>
  !!competition.date_competition && (competition.date_fin || competition.date_competition) < today;

/** Most recent first; undated ones last, then by id (newest first). */
export function sortCompetitions(list: readonly Competition[]): Competition[] {
  return list.slice().sort((a, b) => (b.date_competition ?? "").localeCompare(a.date_competition ?? "") || (b.id ?? 0) - (a.id ?? 0));
}

export type When = "all" | "upcoming" | "past";

/** The list as filtered by the search (name, place, discipline) and the date chips. */
export function filterCompetitions(list: readonly Competition[], search: string, when: When, today: string): Competition[] {
  const q = normKey(search);
  return list.filter((c) => {
    if (when === "upcoming" && isPast(c, today)) {
      return false;
    }
    if (when === "past" && !isPast(c, today)) {
      return false;
    }
    return !q || normKey(`${c.nom} ${c.lieu ?? ""} ${c.type ?? ""} ${c.id_ffme ?? ""}`).includes(q);
  });
}

/** « 15/03/2026 », « 15/03 au 16/03/2026 » (the year once when both days share it), « 31/12/2026 au 01/01/2027 » or
    « sans date ». */
export function periodText(competition: Competition): string {
  const start = competition.date_competition ?? "";
  if (!start) {
    return "sans date";
  }
  const end = competition.date_fin ?? "";
  const startText = formatDayText(start);
  if (!end || end <= start) {
    return startText;
  }
  const endText = formatDayText(end);
  const sameYear = start.slice(0, 4) === end.slice(0, 4) && startText.length === 10;
  return `${sameYear ? startText.slice(0, 5) : startText} au ${endText}`;
}

/** The first month of a sports season: September, as on the server (domain/members/age_rules.py SEASON_START_MONTH). */
const SEASON_START_MONTH = 9;

/** « 2026-2027 » for an ISO date from September 2026 to August 2027; empty for a missing or unreadable date. */
export function seasonOf(iso: string | null | undefined): string {
  const match = /^(\d{4})-(\d{2})/.exec(iso ?? "");
  if (!match) {
    return "";
  }
  const year = Number(match[1]);
  const start = Number(match[2]) >= SEASON_START_MONTH ? year : year - 1;
  return `${start}-${start + 1}`;
}

/** Seasons with competitions, and the current one; most recent first. Undated competitions count in the current one. */
export function seasons(list: readonly Competition[], today: string = todayIso()): string[] {
  const found = new Set([seasonOf(today), ...list.map((c) => seasonOf(c.date_competition)).filter(Boolean)]);
  return [...found].sort((left, right) => right.localeCompare(left));
}

/** The discipline, when it says more than « escalade » (pass-through field of the office page). */
export function shownDiscipline(competition: Competition): string {
  const t = (competition.type ?? "").trim();
  return t && t.toLowerCase() !== "escalade" ? t : "";
}

export const DISCIPLINE_COLOR: Record<string, BadgeColor> = { bloc: "violet", difficulté: "blue", vitesse: "amber", combiné: "teal" };

/** Badge colour of a discipline (former office page colours), blue for any other. */
export const disciplineColor = (name: string): BadgeColor => DISCIPLINE_COLOR[name.toLowerCase()] ?? "blue";

export interface Counts {
  all: number;
  selected: number;
  unpaid: number;
  paid: number;
  present: number;
}

export function counts(parts: readonly Pick<Participant, "selectionne" | "statut_paiement" | "present">[]): Counts {
  return {
    all: parts.length,
    selected: parts.filter((p) => p.selectionne).length,
    unpaid: parts.filter((p) => p.statut_paiement === "en_attente").length,
    paid: parts.filter((p) => p.statut_paiement === "paye").length,
    present: parts.filter((p) => p.present).length,
  };
}

export function hasResults(competition: Competition): boolean {
  return !!competition.resultats_synced_at || (competition.participants ?? []).some((p) => p.resultat_ffme || p.classement);
}

export const PAYMENT: Record<string, { label: string; color: BadgeColor }> = {
  paye: { label: "Payé", color: "green" },
  en_attente: { label: "En attente", color: "amber" },
  non_invite: { label: "Non invité", color: "slate" },
  annule_perdu: { label: "Annulé — perdu", color: "red" },
  annule_reporte: { label: "Annulé — report", color: "violet" },
};

export function paymentBadge(status: string | undefined): { label: string; color: BadgeColor } {
  return PAYMENT[status ?? ""] ?? { label: status || "—", color: "slate" };
}

export const isCancelled = (participant: Participant): boolean =>
  participant.statut_paiement === "annule_reporte" || participant.statut_paiement === "annule_perdu";
/** Money received (HelloAsso or by hand), not cancelled since: the competitor cannot be removed, only withdrawn. */
export const hasPaid = (participant: Participant): boolean =>
  !isCancelled(participant) &&
  (participant.statut_paiement === "paye" || Number(participant.montant_paye ?? 0) > 0 || !!participant.commande_helloasso);
/** Listed but never invited and nothing paid: the office may remove them all at once. */
export const isNotInvited = (participant: Participant): boolean =>
  !participant.selectionne && (!participant.statut_paiement || participant.statut_paiement === "non_invite") && !hasPaid(participant);

const PODIUM: Record<string, { icon: string; color: BadgeColor }> = {
  "1": { icon: "🥇", color: "gold" },
  "2": { icon: "🥈", color: "silver" },
  "3": { icon: "🥉", color: "bronze" },
};

const rankOf = (participant: Participant): string => String(participant.classement ?? "").trim();

/** The medal of a podium place, empty off the podium or without a result. */
export const podiumIcon = (participant: Participant): string => PODIUM[rankOf(participant)]?.icon ?? "";

/** The pill colour of a result: gold, silver, bronze on the podium, light grey otherwise. */
export const rankingColor = (participant: Participant): BadgeColor => PODIUM[rankOf(participant)]?.color ?? "slate";

/** « 1er », « 4 / 23 »… of a MyCompet result (the FFME result without one), empty without either. */
export function rankingLabel(participant: Participant): string {
  const rank = rankOf(participant);
  if (!rank) {
    return String(participant.resultat_ffme ?? "");
  }
  const total = Number(participant.total_categorie ?? 0);
  return `${rank}${total > 0 ? ` / ${total}` : rank === "1" ? "er" : "e"}`;
}

/** « 🥇 1er », « 4 / 23 »…: the label behind the medal of a podium place. */
export function rankingText(participant: Participant): string {
  const label = rankingLabel(participant);
  const icon = podiumIcon(participant);
  return label && icon ? `${icon} ${label}` : label;
}

export interface ContactCard {
  role: "athlete" | "emergency";
  title: string;
  name: string;
  phone: string;
  email: string;
}

/** Who to call for a participant: the competitor entry's contacts when the device has one, else the copy made when
    the member was added. */
function emergencyOf(participant: Participant, contact?: SavedCompetitorContact): EmergencyContactRow[] {
  return emergencyContactsOf(contact ?? { emergency1_name: participant.urgence_nom, emergency1_phone: participant.urgence_tel });
}

/** The contact cards of an athlete: the athlete (with the e-mail of the member list), then one card per emergency
    contact, or an empty one to show there is none (name and phone only: no e-mail is kept offline about a competitor's
    contacts). */
export function athleteContactCards(participant: Participant, member?: MemberSlot, contact?: SavedCompetitorContact): ContactCard[] {
  const emergency = emergencyOf(participant, contact);
  return [
    {
      role: "athlete",
      title: "🧗 Athlète",
      name: `${participant.prenom} ${participant.nom}`.trim() || `${member?.prenom ?? ""} ${member?.nom ?? ""}`.trim(),
      phone: contact?.phone || participant.phone || "",
      email: member?.email || participant.email || "",
    },
    ...(emergency.length
      ? emergency.map((person, index): ContactCard => ({
          role: "emergency",
          title: `🚨 Contact d'urgence ${index + 1}`,
          name: person.name,
          phone: person.phone,
          email: "",
        }))
      : [{ role: "emergency", title: "🚨 Contact d'urgence", name: "", phone: "", email: "" } satisfies ContactCard]),
  ];
}

/** A participant as listed: the member's current tariff and slot group, phone and emergency contacts when known, and
    the changes waiting in the outbox (shown at once, sent when the network comes back). */
export interface Row extends Participant {
  /** The slot group (contact dialog only), "" when not known */
  group: string;
  /** Category and sex of the competitor (« U13 F »), NO_CATEGORY_SECTION or UNIDENTIFIED: their section of the list */
  section: string;
  emergency: { name: string; phone: string }[];
  contacts: ContactCard[];
  /** Flags changed offline, not sent yet */
  queued: { selectionne: boolean; present: boolean };
}

export const UNIDENTIFIED = "Non identifiés";
/** Competitors without a FFME category (under 9, no birth date): after the categories, before UNIDENTIFIED. */
export const NO_CATEGORY_SECTION = "Sans catégorie";

const SEX_ORDER: readonly (Sex | null)[] = ["F", "H", null];

/** Order of a competitor's section: categories youngest first, F then H then unknown sex; then NO_CATEGORY_SECTION, UNIDENTIFIED. */
function sectionRank(row: Pick<Row, "adherent_id" | "categorie" | "sex">): number {
  if (row.adherent_id == null) {
    return Number.MAX_SAFE_INTEGER;
  }
  const category = row.categorie ? CATEGORY_ORDER.indexOf(row.categorie) : -1;
  return category < 0 ? Number.MAX_SAFE_INTEGER - 1 : category * SEX_ORDER.length + SEX_ORDER.indexOf(row.sex ?? null);
}

function sectionOf(participant: Participant): string {
  if (participant.adherent_id == null) {
    return UNIDENTIFIED;
  }
  return categoryAndSexLabel(participant.categorie, participant.sex) || NO_CATEGORY_SECTION;
}

/** Value of a flag changed offline, undefined when none waits. */
export type PendingValue = (adherentId: number | null | undefined, flag: "selectionne" | "present") => boolean | undefined;

/** The participants of a competition with what the other lists know of them. contacts: coaches only (kept offline);
    without them, the emergency contact copied when the member was added. */
export function participantRows(
  competition: Competition,
  members: readonly MemberSlot[],
  contacts: readonly SavedCompetitorContact[],
  pending: PendingValue = () => undefined,
): Row[] {
  const memberOf = new Map(members.map((m) => [m.id, m]));
  const contactOf = new Map(contacts.map((k) => [k.adherent_id, k]));
  return (competition.participants ?? []).map((p) => {
    const member = p.adherent_id != null ? memberOf.get(p.adherent_id) : undefined;
    const contact = p.adherent_id != null ? contactOf.get(p.adherent_id) : undefined;
    const tarif = member?.tarif || p.tarif || "";
    const selectionne = pending(p.adherent_id, "selectionne");
    const present = pending(p.adherent_id, "present");
    return {
      ...p,
      selectionne: selectionne ?? p.selectionne,
      present: present ?? p.present,
      queued: { selectionne: selectionne !== undefined, present: present !== undefined },
      tarif,
      phone: contact?.phone || p.phone || "",
      email: member?.email || member?.email_secondaire || p.email || "",
      group: member?.creneau_groupe || contact?.creneau_groupe || tarif,
      section: sectionOf(p),
      emergency: emergencyOf(p, contact).filter((e) => e.phone),
      contacts: athleteContactCards(p, member, contact),
    };
  });
}

export type ParticipantFilter = "all" | "selected" | "unpaid" | "notInvited";

/** section: one category and sex only (Row.section), every section when empty. */
export function filterRows(rows: readonly Row[], filter: ParticipantFilter, search = "", section = ""): Row[] {
  const q = normKey(search);
  return rows.filter((r) => {
    if (section && r.section !== section) {
      return false;
    }
    if (filter === "selected" && !r.selectionne) {
      return false;
    }
    if (filter === "unpaid" && r.statut_paiement !== "en_attente") {
      return false;
    }
    if (filter === "notInvited" && !isNotInvited(r)) {
      return false;
    }
    return !q || normKey(`${r.nom} ${r.prenom} ${r.num_licence ?? ""}`).includes(q);
  });
}

/** By last name then first name, French order. */
export function byName(left: Pick<Participant, "nom" | "prenom">, right: Pick<Participant, "nom" | "prenom">): number {
  return (left.nom ?? "").localeCompare(right.nom ?? "", "fr") || (left.prenom ?? "").localeCompare(right.prenom ?? "", "fr");
}

/** By section (category and sex, youngest first: sectionRank), each sorted by name. */
export function categoryRows(rows: readonly Row[]): [string, Row[]][] {
  const sections = new Map<string, Row[]>();
  for (const r of [...rows].sort((a, b) => sectionRank(a) - sectionRank(b))) {
    sections.set(r.section, [...(sections.get(r.section) ?? []), r]);
  }
  return [...sections.entries()].map(([section, list]) => [section, list.sort(byName)]);
}

/** The sections to pick from (phones and computers), in the order of the list; n: their competitors. */
export function categoryFilters(rows: readonly Row[]): { section: string; n: number }[] {
  return categoryRows(rows).map(([section, list]) => ({ section, n: list.length }));
}

const FILTER_SUFFIXES: Record<ParticipantFilter, string> = {
  all: "",
  selected: " (participe : oui)",
  unpaid: " (paiement en attente)",
  notInvited: " (non invités)",
};

export function countLine(counts: Counts, filter: ParticipantFilter, shown: number, section = ""): string {
  if (section) {
    return `${shown} compétiteur${plural(shown)} en « ${section} »${FILTER_SUFFIXES[filter]}`;
  }
  if (filter === "selected") {
    return `${counts.selected} compétiteur${plural(counts.selected)} sélectionné${plural(counts.selected)}`;
  }
  if (filter === "unpaid") {
    return `${counts.unpaid} compétiteur${plural(counts.unpaid)} avec paiement en attente`;
  }
  if (filter === "notInvited") {
    return `${shown} compétiteur${plural(shown)} non invité${plural(shown)}`;
  }
  return `${counts.selected} compétiteur${plural(counts.selected)} sélectionné${plural(counts.selected)} sur ${counts.all}`;
}

/** Members matching the search (name, first name, licence; 2 letters at least), not listed yet, 15 at most. */
export function memberMatches(members: readonly MemberSlot[], competition: Competition, search: string): MemberSlot[] {
  const q = normKey(search);
  if (q.length < 2) {
    return [];
  }
  const listed = new Set((competition.participants ?? []).map((p) => p.adherent_id));
  return members
    .filter(
      (m) =>
        !listed.has(m.id) &&
        (normKey(`${m.nom} ${m.prenom}`).includes(q) || normKey(`${m.prenom} ${m.nom}`).includes(q) || normKey(m.licence_ffme).includes(q)),
    )
    .sort(byName)
    .slice(0, 15);
}

/** The competition's participants as a spreadsheet (office export). */
export function participantCsv(rows: readonly Row[]): Cell[][] {
  return [
    ["Nom", "Prénom", "N° Licence", "Catégorie", "Résultat FFME", "Participe", "Paiement", "Montant", "Commande", "Présent", "Téléphone"],
    ...categoryRows(rows)
      .flatMap(([, list]) => list)
      .map((p) => [
        p.nom,
        p.prenom,
        p.num_licence,
        p.section === UNIDENTIFIED || p.section === NO_CATEGORY_SECTION ? "" : p.section,
        rankingLabel(p),
        p.selectionne ? "Oui" : "Non",
        paymentBadge(p.statut_paiement).label,
        p.montant_paye ? `${p.montant_paye} €` : "",
        p.commande_helloasso,
        p.present ? "Présent" : "Absent",
        p.phone,
      ]),
  ];
}

export const csvName = (competition: Competition): string => `competition_${String(competition.nom || "export").replace(/\W+/g, "_")}.csv`;

// ---------------------------------------------------------------- Create / edit form

export const DISCIPLINES = ["Bloc", "Difficulté", "Vitesse", "Combiné", "Escalade"] as const;

/** 7 days before the start date (YYYY-MM-DD), or empty string when undated. */
export function defaultDeadline(start: string): string {
  if (!start || !/^\d{4}-\d{2}-\d{2}$/.test(start)) {
    return "";
  }
  const deadline = new Date(`${start}T00:00:00`);
  deadline.setDate(deadline.getDate() - 7);
  return todayIso(deadline);
}

/** The registration deadline of a competition, the default one when none is stored (cached before the field existed). */
export function deadlineOf(competition: Competition): string {
  return competition.deadline || defaultDeadline(competition.date_competition ?? "");
}

export interface CompetitionDraft {
  nom: string;
  id_ffme: string;
  date_competition: string;
  date_fin: string;
  deadline: string;
  lieu: string;
  type: string;
  prix: string;
  url_resultats: string;
  whatsapp_link: string;
  coach_ids: number[];
}

export function draftOf(competition?: Competition): CompetitionDraft {
  const start = competition?.date_competition ?? "";
  return {
    nom: competition?.nom ?? "",
    id_ffme: competition?.id_ffme ?? "",
    date_competition: start,
    date_fin: competition?.date_fin && competition.date_fin !== competition.date_competition ? competition.date_fin : "",
    deadline: competition?.deadline || defaultDeadline(start),
    lieu: competition?.lieu ?? "",
    type: competition?.type ?? "",
    prix: competition ? String(competition.prix ?? 0) : "",
    url_resultats: competition?.url_resultats ?? "",
    whatsapp_link: competition?.whatsapp_link ?? "",
    coach_ids: [...(competition?.coach_ids ?? [])],
  };
}

export function draftErrors(draft: CompetitionDraft): Partial<Record<keyof CompetitionDraft, string>> {
  const errors: Partial<Record<keyof CompetitionDraft, string>> = {};
  if (!draft.nom.trim()) {
    errors.nom = "Le nom de l'épreuve est obligatoire.";
  }
  if (draft.prix.trim() && !(Number(draft.prix.replace(",", ".")) >= 0)) {
    errors.prix = "Montant invalide.";
  }
  if (draft.date_fin && !draft.date_competition) {
    errors.date_fin = "Indiquez d'abord la date de début.";
  }
  return errors;
}

/** Body of POST /api/competitions and PATCH /api/competitions/{id}: an end before the start (or none) is the start. */
export function draftBody(draft: CompetitionDraft): Schemas["CompetitionCreate"] {
  const start = draft.date_competition;
  return {
    nom: draft.nom.trim(),
    id_ffme: draft.id_ffme.trim(),
    date_competition: start,
    date_fin: start && draft.date_fin > start ? draft.date_fin : start,
    // Only a deadline set by hand is stored: the default one follows the start date
    deadline: draft.deadline === defaultDeadline(start) ? "" : draft.deadline,
    lieu: draft.lieu.trim(),
    type: draft.type,
    prix: Number(draft.prix.replace(",", ".")) || 0,
    url_resultats: draft.url_resultats.trim(),
    whatsapp_link: draft.whatsapp_link.trim(),
    coach_ids: draft.coach_ids,
  };
}

/** The coaches to tick: the competition's own first, in their saved order (kept on save), then the others by name. */
export function coachChoices(coaches: readonly Coach[], selected: readonly number[]): Coach[] {
  const byId = new Map(coaches.map((c) => [c.id, c]));
  const first = selected.map((id) => byId.get(id)).filter((c): c is Coach => !!c);
  const others = coaches.filter((c) => !selected.includes(c.id)).sort((a, b) => (a.nom ?? "").localeCompare(b.nom ?? "", "fr"));
  return [...first, ...others];
}

/** The competitions a coach follows. */
export const coachedBy = (list: readonly Competition[], coach: Coach): Competition[] =>
  list.filter((c) => (c.coach_ids ?? []).includes(coach.id));

/** A MyCompet results page, or its number (13660), as the server takes it. */
export const resultsUrlHint = "https://mycompet.ffme.fr/resultat/resultat_13660 ou 13660";
