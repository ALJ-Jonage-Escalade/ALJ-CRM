/* Directory (/index): the members of a season for coaches and admins, read only, kept on the device for offline
   reading (plan D2). Only the fields shown here are kept: contacts, emergency contacts and diplomas. No health data
   and no payment (amount, order): they stay online, in the member record of Adhérents.
   Filters, search and display helpers are the ones of Adhérents (adherents/members.ts). */
import { normKey } from "../../lib/text";
import type { Creneau, Member, MemberList } from "../adherents/members";
import { formatDayText } from "../../lib/format";

const FIELDS = [
  "user_id",
  "purchase_id",
  "season_name",
  "last_name",
  "first_name",
  "birth_date",
  "tarif_name",
  "creneau_groupe",
  "status_norm",
  "address",
  "zip_code",
  "city",
  "phone",
  "email_primary",
  "email_secondary",
  "licence_ffme",
  "emergency1_name",
  "emergency1_phone",
  "emergency2_name",
  "emergency2_phone",
  "photo_auth",
  "badge_rouge",
  "autonomie_bloc",
  "passeport_orange",
  "raw_passports",
  "payer",
  "payer_email",
] as const satisfies readonly (keyof Member)[];

export type DirectoryMember = Pick<Member, (typeof FIELDS)[number]>;

export interface Directory {
  season: string;
  creneaux: Creneau[];
  members: DirectoryMember[];
}

/** The answer of GET /api/members reduced to what the directory shows (and keeps on the device). */
export function toDirectory(list: MemberList): Directory {
  return {
    season: list.season,
    creneaux: list.creneaux,
    members: list.members.map((m) => Object.fromEntries(FIELDS.map((k) => [k, m[k]])) as DirectoryMember),
  };
}

/** Members of the season, cancelled ones apart (the KPIs of the former page). */
export function seasonCounts(members: readonly Pick<Member, "status_norm">[]): { registered: number; cancelled: number } {
  const cancelled = members.filter((m) => m.status_norm === "Annulé").length;
  return { registered: members.length - cancelled, cancelled };
}

const joined = (parts: (string | null | undefined)[], sep: string) => parts.filter(Boolean).join(sep);

/** Lines of a member's card, unfolded: the empty ones are left out. */
export function detailRows(member: DirectoryMember): { label: string; value: string }[] {
  const rows: [string, string][] = [
    ["🎂 Naissance", formatDayText(member.birth_date)],
    ["📍 Adresse", joined([member.address, joined([member.zip_code, member.city], " ")], ", ")],
    ["📞 Téléphone", member.phone],
    ["✉️ E-mail", member.email_primary],
    ["✉️ E-mail 2", member.email_secondary],
    ["🪪 Licence FFME", member.licence_ffme],
    ["🚨 Urgence 1", joined([member.emergency1_name, member.emergency1_phone], " · ")],
    ["🚨 Urgence 2", joined([member.emergency2_name, member.emergency2_phone], " · ")],
    ["📷 Droit à l'image", member.photo_auth],
    ["🔴 Badge rouge", member.badge_rouge],
    ["🧗 Autonomie bloc", member.autonomie_bloc],
  ];
  // The payer when it is someone else (a parent): another contact
  if (member.payer && normKey(member.payer) !== normKey(`${member.first_name} ${member.last_name}`)) {
    rows.push(["💳 Payeur", member.payer + (member.payer_email ? ` (${member.payer_email})` : "")]);
  }
  return rows.filter(([, value]) => value.trim() !== "").map(([label, value]) => ({ label, value }));
}

/** Phones to call for a member: their own, then the emergency contacts. */
export function emergencyRows(member: DirectoryMember): { label: string; name: string; phone: string }[] {
  return [
    { label: "👤 Adhérent", name: "", phone: member.phone },
    { label: "🚨 Urgence 1", name: member.emergency1_name, phone: member.emergency1_phone },
    { label: "🚨 Urgence 2", name: member.emergency2_name, phone: member.emergency2_phone },
  ].filter((r) => r.name || r.phone);
}

/** The emergency tab searches names only, from 2 letters: it lists nobody before. */
export const EMERGENCY_MIN_LETTERS = 2;

export function emergencyMatches<M extends Pick<Member, "first_name" | "last_name">>(members: readonly M[], search: string): M[] | null {
  const q = normKey(search);
  if (q.length < EMERGENCY_MIN_LETTERS) {
    return null;
  }
  return members.filter((m) => {
    const last = normKey(m.last_name);
    const first = normKey(m.first_name);
    return last.includes(q) || first.includes(q) || `${first} ${last}`.includes(q) || `${last} ${first}`.includes(q);
  });
}

/** Same key as the former directory page (web/index.html): the filters of earlier visits are kept. */
export const DIRECTORY_FILTERS_STORAGE = "alj_annuaire_filters";
