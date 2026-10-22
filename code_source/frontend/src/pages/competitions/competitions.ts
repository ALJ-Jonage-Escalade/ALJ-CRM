/* Competitions screen (read only): the competitions, their participants and payment status, as the former pages
   showed them (web/competitions.html, web/bureau/competitions.html). Writes stay on those pages until plan phase 11. */
import type { Schemas } from "../../lib/client";

export type Competition = Schemas["Competition"];
export type Participant = Schemas["CompetitionParticipant"];
export type CompetitorContact = Schemas["CompetitorContact"];
/** What the screen keeps of the member directory (GET /api/competition-members): the current tariff and slot group. */
export type MemberSlot = Pick<Schemas["CompetitionMember"], "id" | "tarif" | "creneau_groupe">;

export const ARCHIVED = "close";

/** The answer of GET /api/competition-members reduced to the grouping fields (contacts stay on the server). */
export function toMemberSlots(answer: unknown): MemberSlot[] {
  return (answer as Schemas["CompetitionMember"][]).map((m) => ({ id: m.id, tarif: m.tarif ?? "", creneau_groupe: m.creneau_groupe ?? "" }));
}

export const isArchived = (c: Competition): boolean => c.statut === ARCHIVED;

/** Most recent first; undated ones last, then by id (newest first). */
export function sortCompetitions(list: readonly Competition[]): Competition[] {
  return list
    .slice()
    .sort((a, b) => (b.date_competition ?? "").localeCompare(a.date_competition ?? "") || (b.id ?? 0) - (a.id ?? 0));
}

const frDate = (iso: string) => iso.split("-").reverse().join("/");

/** « 15/03/2026 », « 15/03/2026 → 16/03/2026 » or « sans date ». */
export function period(c: Competition): string {
  const start = c.date_competition ?? "";
  if (!start) return "sans date";
  const end = c.date_fin ?? "";
  return end && end > start ? `${frDate(start)} → ${frDate(end)}` : frDate(start);
}

export const euros = (n: number | null | undefined): string =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(Number(n ?? 0));

export interface Counts {
  all: number;
  selected: number;
  unpaid: number;
  paid: number;
}

export function counts(parts: readonly Pick<Participant, "selectionne" | "statut_paiement">[]): Counts {
  return {
    all: parts.length,
    selected: parts.filter((p) => p.selectionne).length,
    unpaid: parts.filter((p) => p.statut_paiement === "en_attente").length,
    paid: parts.filter((p) => p.statut_paiement === "paye").length,
  };
}

export function hasResults(c: Competition): boolean {
  return !!c.resultats_synced_at || (c.participants ?? []).some((p) => p.resultat_ffme || p.classement);
}

export const PAYMENT: Record<string, { label: string; class: string }> = {
  paye: { label: "Payé", class: "bg-green-600" },
  en_attente: { label: "En attente", class: "bg-amber-600" },
  non_invite: { label: "Non invité", class: "bg-slate-400" },
  annule_perdu: { label: "Annulé — perdu", class: "bg-red-600" },
  annule_reporte: { label: "Annulé — report", class: "bg-violet-600" },
};

export function payment(status: string | undefined): { label: string; class: string } {
  return PAYMENT[status ?? ""] ?? { label: status || "—", class: "bg-slate-400" };
}

/** A participant as listed: the member's current tariff and slot group, phone and emergency contacts when known. */
export interface Row extends Participant {
  group: string;
  emergency: { name: string; phone: string }[];
}

export const UNIDENTIFIED = "Non identifiés";

/** The participants of a competition with what the other lists know of them. contacts: coaches only (kept offline);
    without them, the emergency contact copied when the member was added. */
export function participantRows(c: Competition, members: readonly MemberSlot[], contacts: readonly CompetitorContact[]): Row[] {
  const memberOf = new Map(members.map((m) => [m.id, m]));
  const contactOf = new Map(contacts.map((k) => [k.adherent_id, k]));
  return (c.participants ?? []).map((p) => {
    const member = p.adherent_id != null ? memberOf.get(p.adherent_id) : undefined;
    const contact = p.adherent_id != null ? contactOf.get(p.adherent_id) : undefined;
    const tarif = member?.tarif || p.tarif || "";
    const emergency = contact
      ? [{ name: contact.emergency1_name, phone: contact.emergency1_phone }, { name: contact.emergency2_name, phone: contact.emergency2_phone }]
      : [{ name: p.urgence_nom ?? "", phone: p.urgence_tel ?? "" }];
    return {
      ...p,
      tarif,
      phone: contact?.phone || p.phone || "",
      group: member?.creneau_groupe || contact?.creneau_groupe || tarif || UNIDENTIFIED,
      emergency: emergency.filter((e) => e.phone),
    };
  });
}

export type ParticipantFilter = "all" | "selected" | "unpaid";

export function filterRows(rows: readonly Row[], filter: ParticipantFilter): Row[] {
  if (filter === "selected") return rows.filter((r) => r.selectionne);
  if (filter === "unpaid") return rows.filter((r) => r.statut_paiement === "en_attente");
  return rows.slice();
}

/** By slot group (French order, « Non identifiés » last), each sorted by name. */
export function groupRows(rows: readonly Row[]): [string, Row[]][] {
  const groups = new Map<string, Row[]>();
  for (const r of rows) groups.set(r.group, [...(groups.get(r.group) ?? []), r]);
  const byName = (a: Row, b: Row) => (a.nom ?? "").localeCompare(b.nom ?? "", "fr") || (a.prenom ?? "").localeCompare(b.prenom ?? "", "fr");
  return [...groups.entries()]
    .sort(([a], [b]) => Number(a === UNIDENTIFIED) - Number(b === UNIDENTIFIED) || a.localeCompare(b, "fr"))
    .map(([g, list]) => [g, list.sort(byName)]);
}

export function countLine(c: Counts, filter: ParticipantFilter): string {
  const s = (n: number) => (n > 1 ? "s" : "");
  if (filter === "selected") return `${c.selected} compétiteur${s(c.selected)} sélectionné${s(c.selected)}`;
  if (filter === "unpaid") return `${c.unpaid} compétiteur${s(c.unpaid)} avec paiement en attente`;
  return `${c.selected} compétiteur${s(c.selected)} sélectionné${s(c.selected)} sur ${c.all}`;
}

/** Where the competitions are changed until plan phase 11: the former phone page, or the former office page. */
export const MANAGE_PHONE = "/competitions/gestion";
export const MANAGE_DESKTOP = "/bureau/competitions-gestion";
