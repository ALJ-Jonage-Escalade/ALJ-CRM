/* Competitions screen: the competitions, their participants and payment status, and what coaches change on them (the
   former pages web/competitions.html and web/bureau/competitions.html, merged). The server checks every change. */
import type { BadgeColor } from "../../components/ui/UiBadge.vue";
import type { Cell } from "../../lib/csv";
import type { Schemas } from "../../lib/client";
import { formatDayText } from "../../lib/format";
import { normKey } from "../adherents/members";
import { plural } from "../../lib/text";

export type Competition = Schemas["Competition"];
export type Participant = Schemas["CompetitionParticipant"];
export type CompetitorContact = Schemas["CompetitorContact"];
export type Coach = Schemas["Coach"];
/** What the screen keeps of the member directory (GET /api/competition-members, online only): the current tariff and
    slot group to group the participants, the names, licence and e-mail to add one or write to them. */
export type MemberSlot = Pick<
  Schemas["CompetitionMember"],
  "id" | "nom" | "prenom" | "licence_ffme" | "email" | "email_secondaire" | "tarif" | "creneau_groupe"
>;

export const ARCHIVED = "close";
export const PREPARING = "en_preparation";

/** The answer of GET /api/competition-members reduced to the fields above (phones and emergency contacts stay on the server). */
export function toMemberSlots(answer: unknown): MemberSlot[] {
  return (answer as Schemas["CompetitionMember"][]).map((m) => ({
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

export const isArchived = (c: Competition): boolean => c.statut === ARCHIVED;

/** Today as YYYY-MM-DD, local time. */
export function todayIso(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Over: ended before today (undated ones never are). */
export const isPast = (c: Competition, today: string): boolean => !!c.date_competition && (c.date_fin || c.date_competition) < today;

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

/** « 15/03/2026 », « 15/03/2026 → 16/03/2026 » or « sans date ». */
export function period(c: Competition): string {
  const start = c.date_competition ?? "";
  if (!start) {
    return "sans date";
  }
  const end = c.date_fin ?? "";
  return end && end > start ? `${formatDayText(start)} → ${formatDayText(end)}` : formatDayText(start);
}

/** « 31/10/2026 » ou « 31/10 au 01/11/2026 » si sur deux jours. */
export function formatCompetitionPeriod(c: Competition): string {
  const start = c.date_competition ?? "";
  if (!start) {
    return "sans date";
  }
  const end = c.date_fin ?? "";
  const startText = formatDayText(start);
  if (!end || end <= start) {
    return startText;
  }
  const endText = formatDayText(end);
  if (startText.length === 10 && endText.length === 10 && startText.slice(6) === endText.slice(6)) {
    return `${startText.slice(0, 5)} au ${endText}`;
  }
  return `${startText} au ${endText}`;
}

/** Calcule la saison sportive (ex. 2026-2027) à partir d'une date ISO. */
export function competitionSeason(dateStr?: string): string {
  if (!dateStr) {
    return "";
  }
  const parts = dateStr.slice(0, 10).split("-");
  if (parts.length < 3) {
    return "";
  }
  const yearStr = parts[0];
  const monthStr = parts[1];
  if (!yearStr || !monthStr) {
    return "";
  }
  const year = parseInt(yearStr, 10);
  const month = parseInt(monthStr, 10);
  if (isNaN(year) || isNaN(month)) {
    return "";
  }
  return month >= 9 ? `${year}-${year + 1}` : `${year - 1}-${year}`;
}

/** The discipline, when it says more than « escalade » (pass-through field of the office page). */
export function discipline(c: Competition): string {
  const t = (c.type ?? "").trim();
  return t && t.toLowerCase() !== "escalade" ? t : "";
}

const DISCIPLINE_COLOR: Record<string, BadgeColor> = { bloc: "violet", difficulté: "blue", vitesse: "amber", combiné: "teal" };

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

export function hasResults(c: Competition): boolean {
  return !!c.resultats_synced_at || (c.participants ?? []).some((p) => p.resultat_ffme || p.classement);
}

export const PAYMENT: Record<string, { label: string; color: BadgeColor }> = {
  paye: { label: "Payé", color: "green" },
  en_attente: { label: "En attente", color: "amber" },
  non_invite: { label: "Non invité", color: "slate" },
  annule_perdu: { label: "Annulé — perdu", color: "red" },
  annule_reporte: { label: "Annulé — report", color: "violet" },
};

export function payment(status: string | undefined): { label: string; color: BadgeColor } {
  return PAYMENT[status ?? ""] ?? { label: status || "—", color: "slate" };
}

export const isCancelled = (p: Participant): boolean => p.statut_paiement === "annule_reporte" || p.statut_paiement === "annule_perdu";
/** Money received (HelloAsso or by hand), not cancelled since: the competitor cannot be removed, only withdrawn. */
export const hasPaid = (p: Participant): boolean =>
  !isCancelled(p) && (p.statut_paiement === "paye" || Number(p.montant_paye ?? 0) > 0 || !!p.commande_helloasso);
/** Listed but never invited and nothing paid: the office may remove them all at once. */
export const isNotInvited = (p: Participant): boolean =>
  !p.selectionne && (!p.statut_paiement || p.statut_paiement === "non_invite") && !hasPaid(p);

/** « 🥇 1er », « 🏅 4 / 23 »… of a MyCompet result, empty without one. */
export function ranking(p: Participant): string {
  const r = String(p.classement ?? "").trim();
  if (!r) {
    return p.resultat_ffme ? `🏅 ${p.resultat_ffme}` : "";
  }
  const icon = r === "1" ? "🥇" : r === "2" ? "🥈" : r === "3" ? "🥉" : "🏅";
  const total = Number(p.total_categorie ?? 0);
  return `${icon} ${r}${total > 0 ? ` / ${total}` : r === "1" ? "er" : "e"}`;
}

/** A participant as listed: the member's current tariff and slot group, phone and emergency contacts when known, and
    the changes waiting in the outbox (shown at once, sent when the network comes back). */
export interface Row extends Participant {
  group: string;
  emergency: { name: string; phone: string }[];
  /** Flags changed offline, not sent yet */
  queued: { selectionne: boolean; present: boolean };
}

export const UNIDENTIFIED = "Non identifiés";

/** Value of a flag changed offline, undefined when none waits. */
export type PendingValue = (adherentId: number | null | undefined, flag: "selectionne" | "present") => boolean | undefined;

/** The participants of a competition with what the other lists know of them. contacts: coaches only (kept offline);
    without them, the emergency contact copied when the member was added. */
export function participantRows(
  c: Competition,
  members: readonly MemberSlot[],
  contacts: readonly CompetitorContact[],
  pending: PendingValue = () => undefined,
): Row[] {
  const memberOf = new Map(members.map((m) => [m.id, m]));
  const contactOf = new Map(contacts.map((k) => [k.adherent_id, k]));
  return (c.participants ?? []).map((p) => {
    const member = p.adherent_id != null ? memberOf.get(p.adherent_id) : undefined;
    const contact = p.adherent_id != null ? contactOf.get(p.adherent_id) : undefined;
    const tarif = member?.tarif || p.tarif || "";
    const emergency = contact
      ? [
          { name: contact.emergency1_name, phone: contact.emergency1_phone },
          { name: contact.emergency2_name, phone: contact.emergency2_phone },
        ]
      : [{ name: p.urgence_nom ?? "", phone: p.urgence_tel ?? "" }];
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
      group: member?.creneau_groupe || contact?.creneau_groupe || tarif || UNIDENTIFIED,
      emergency: emergency.filter((e) => e.phone),
    };
  });
}

export type ParticipantFilter = "all" | "selected" | "unpaid" | "notInvited";

export function filterRows(rows: readonly Row[], filter: ParticipantFilter, search = ""): Row[] {
  const q = normKey(search);
  return rows.filter((r) => {
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

/** By slot group (French order, « Non identifiés » last), each sorted by name. */
export function groupRows(rows: readonly Row[]): [string, Row[]][] {
  const groups = new Map<string, Row[]>();
  for (const r of rows) {
    groups.set(r.group, [...(groups.get(r.group) ?? []), r]);
  }
  const byName = (a: Row, b: Row) => (a.nom ?? "").localeCompare(b.nom ?? "", "fr") || (a.prenom ?? "").localeCompare(b.prenom ?? "", "fr");
  return [...groups.entries()]
    .sort(([a], [b]) => Number(a === UNIDENTIFIED) - Number(b === UNIDENTIFIED) || a.localeCompare(b, "fr"))
    .map(([g, list]) => [g, list.sort(byName)]);
}

export function countLine(c: Counts, filter: ParticipantFilter, shown: number): string {
  if (filter === "selected") {
    return `${c.selected} compétiteur${plural(c.selected)} sélectionné${plural(c.selected)}`;
  }
  if (filter === "unpaid") {
    return `${c.unpaid} compétiteur${plural(c.unpaid)} avec paiement en attente`;
  }
  if (filter === "notInvited") {
    return `${shown} compétiteur${plural(shown)} non invité${plural(shown)}`;
  }
  return `${c.selected} compétiteur${plural(c.selected)} sélectionné${plural(c.selected)} sur ${c.all}`;
}

/** Members matching the search (name, first name, licence; 2 letters at least), not listed yet, 15 at most. */
export function memberMatches(members: readonly MemberSlot[], c: Competition, search: string): MemberSlot[] {
  const q = normKey(search);
  if (q.length < 2) {
    return [];
  }
  const listed = new Set((c.participants ?? []).map((p) => p.adherent_id));
  return members
    .filter(
      (m) =>
        !listed.has(m.id) &&
        (normKey(`${m.nom} ${m.prenom}`).includes(q) || normKey(`${m.prenom} ${m.nom}`).includes(q) || normKey(m.licence_ffme).includes(q)),
    )
    .sort((a, b) => (a.nom ?? "").localeCompare(b.nom ?? "", "fr") || (a.prenom ?? "").localeCompare(b.prenom ?? "", "fr"))
    .slice(0, 15);
}

/** The competition's participants as a spreadsheet (office export). */
export function participantCsv(rows: readonly Row[]): Cell[][] {
  return [
    ["Nom", "Prénom", "N° Licence", "Créneau", "Résultat FFME", "Participe", "Paiement", "Montant", "Commande", "Présent", "Téléphone"],
    ...groupRows(rows)
      .flatMap(([, list]) => list)
      .map((p) => [
        p.nom,
        p.prenom,
        p.num_licence,
        p.group === UNIDENTIFIED ? "" : p.group,
        ranking(p).replace(/^\S+ /, ""),
        p.selectionne ? "Oui" : "Non",
        payment(p.statut_paiement).label,
        p.montant_paye ? `${p.montant_paye} €` : "",
        p.commande_helloasso,
        p.present ? "Présent" : "Absent",
        p.phone,
      ]),
  ];
}

export const csvName = (c: Competition): string => `competition_${String(c.nom || "export").replace(/\W+/g, "_")}.csv`;

// ---------------------------------------------------------------- Create / edit form

export const DISCIPLINES = ["Bloc", "Difficulté", "Vitesse", "Combiné", "Escalade"] as const;

export interface CompetitionDraft {
  nom: string;
  id_ffme: string;
  date_competition: string;
  date_fin: string;
  lieu: string;
  type: string;
  prix: string;
  url_resultats: string;
  whatsapp_link: string;
  coach_ids: number[];
}

export function draftOf(c?: Competition): CompetitionDraft {
  return {
    nom: c?.nom ?? "",
    id_ffme: c?.id_ffme ?? "",
    date_competition: c?.date_competition ?? "",
    date_fin: c?.date_fin && c.date_fin !== c.date_competition ? c.date_fin : "",
    lieu: c?.lieu ?? "",
    type: c?.type ?? "",
    prix: c ? String(c.prix ?? 0) : "",
    url_resultats: c?.url_resultats ?? "",
    whatsapp_link: c?.whatsapp_link ?? "",
    coach_ids: [...(c?.coach_ids ?? [])],
  };
}

export function draftErrors(d: CompetitionDraft): Partial<Record<keyof CompetitionDraft, string>> {
  const errors: Partial<Record<keyof CompetitionDraft, string>> = {};
  if (!d.nom.trim()) {
    errors.nom = "Le nom de l'épreuve est obligatoire.";
  }
  if (d.prix.trim() && !(Number(d.prix.replace(",", ".")) >= 0)) {
    errors.prix = "Montant invalide.";
  }
  if (d.date_fin && !d.date_competition) {
    errors.date_fin = "Indiquez d'abord la date de début.";
  }
  return errors;
}

/** Body of POST /api/competitions and PATCH /api/competitions/{id}: an end before the start (or none) is the start. */
export function draftBody(d: CompetitionDraft): Schemas["CompetitionCreate"] {
  const start = d.date_competition;
  return {
    nom: d.nom.trim(),
    id_ffme: d.id_ffme.trim(),
    date_competition: start,
    date_fin: start && d.date_fin > start ? d.date_fin : start,
    lieu: d.lieu.trim(),
    type: d.type,
    prix: Number(d.prix.replace(",", ".")) || 0,
    url_resultats: d.url_resultats.trim(),
    whatsapp_link: d.whatsapp_link.trim(),
    coach_ids: d.coach_ids,
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
