/* HelloAsso payments of the competitions (« HelloAsso »): the items of the annual campaign (GET /api/helloasso/items,
   mirrored by POST /api/helloasso/sync), linked to a participant automatically or by a coach, or ignored. Port of the
   former phone page's HelloAsso tab. HelloAsso custom fields carry the answer in `answer` or `value`: both are read. */
import type { Schemas } from "../../lib/client";
import { normKey } from "../adherents/members";
import { sortCompetitions, type Competition, type MemberSlot } from "./competitions";

export type HelloAssoItem = Schemas["HelloAssoItem"];

export const isLinked = (it: HelloAssoItem): boolean => it.competition_id != null && it.adherent_id != null;
/** Set aside by a coach (test, purchase unrelated to a competition…). */
export const isIgnored = (it: HelloAssoItem): boolean => it.ignore === true && !isLinked(it);

export interface Field {
  name: string;
  answer: string;
}

export interface ItemInfo {
  beneficiary: string;
  payerName: string;
  payerEmail: string;
  payerCity: string;
  orderId: string;
  date: string;
  formName: string;
  itemName: string;
  state: string;
  amount: number;
  initialAmount: number | null;
  payments: { id: string; amount: number | null; state: string; date: string; means: string }[];
  fields: Field[];
  options: { name: string; amount: number | null; fields: Field[] }[];
  /** HelloAsso's item as received, empty when only the amount came */
  raw: Record<string, unknown>;
}

type Raw = Record<string, unknown>;
const obj = (v: unknown): Raw => (v && typeof v === "object" && !Array.isArray(v) ? (v as Raw) : {});
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
// Scalars only: a nested object has no meaningful text
const text = (v: unknown): string => (typeof v === "string" ? v : typeof v === "number" || typeof v === "boolean" ? String(v) : "");
const cents = (v: unknown): number | null => (v == null || v === "" || Number.isNaN(Number(v)) ? null : Number(v) / 100);
const fullName = (o: Raw) => [o.firstName, o.lastName].filter(Boolean).map(text).join(" ").trim();
const fields = (v: unknown): Field[] =>
  list(v).map((c) => ({ name: text(obj(c).name).trim(), answer: text(obj(c).answer ?? obj(c).value) }));

function parseRaw(it: HelloAssoItem): Raw {
  try {
    return obj(it.raw_json ? JSON.parse(it.raw_json) : null);
  } catch {
    return {};
  }
}

/** Everything known of an item: the mirror's fields, completed by HelloAsso's raw item. */
export function itemInfo(it: HelloAssoItem): ItemInfo {
  const r = parseRaw(it);
  const order = obj(r.order);
  const payer = obj(r.payer);
  const payments = list(r.payments).map(obj);
  return {
    beneficiary: fullName(obj(r.user)) || `${it.payer_prenom ?? ""} ${it.payer_nom ?? ""}`.trim(),
    payerName: fullName(payer),
    payerEmail: text(payer.email),
    payerCity: [payer.zipCode, payer.city].filter(Boolean).map(text).join(" "),
    orderId: text(it.order_id ?? order.id),
    date: it.date_item || text(order.date) || text(payments[0]?.date),
    formName: text(order.formName || order.formSlug || it.campagne_slug),
    itemName: text(r.name),
    state: it.etat || text(r.state),
    amount: Number(it.montant ?? 0),
    initialAmount: cents(r.initialAmount),
    payments: payments.map((p) => ({
      id: text(p.id),
      amount: cents(p.amount ?? p.shareAmount),
      state: text(p.state),
      date: text(p.date),
      means: text(p.paymentMeans),
    })),
    fields: fields(r.customFields),
    options: list(r.options)
      .map(obj)
      .map((o) => ({ name: text(o.name), amount: cents(o.amount), fields: fields(o.customFields) })),
    raw: r,
  };
}

export function displayName(it: HelloAssoItem, info: ItemInfo = itemInfo(it)): string {
  return info.beneficiary || info.payerName || `Article #${it.id_item}`;
}

const STATES: Record<string, string> = {
  processed: "Payé",
  registered: "Enregistré",
  authorized: "Autorisé",
  refused: "Refusé",
  refunded: "Remboursé",
  refunding: "Remboursement en cours",
  canceled: "Annulé",
  contested: "Contesté",
  waiting: "En attente",
};

export function stateLabel(state: string): string {
  const label = STATES[state.toLowerCase()];
  return label ? `${label} (${state})` : state;
}

export type ItemFilter = "unlinked" | "linked" | "ignored" | "all";

export interface ItemCounts {
  all: number;
  linked: number;
  unlinked: number;
  ignored: number;
}

export function itemCounts(items: readonly HelloAssoItem[]): ItemCounts {
  const linked = items.filter(isLinked).length;
  const ignored = items.filter(isIgnored).length;
  return { all: items.length, linked, ignored, unlinked: items.length - linked - ignored };
}

/** The items shown: by filter (« all » without the ignored ones unless asked) and search, the ones to link first, then the newest. */
export function filterItems(
  items: readonly HelloAssoItem[],
  filter: ItemFilter,
  hideIgnored: boolean,
  search: string,
  competitions: readonly Competition[],
  members: readonly MemberSlot[],
): HelloAssoItem[] {
  const q = normKey(search);
  const compName = new Map(competitions.map((c) => [c.id, c.nom ?? ""]));
  const member = new Map(members.map((m) => [m.id, `${m.nom} ${m.prenom}`]));
  const shown = items.filter((it) => {
    if (filter === "unlinked" && (isLinked(it) || isIgnored(it))) {
      return false;
    }
    if (filter === "linked" && !isLinked(it)) {
      return false;
    }
    if (filter === "ignored" && !isIgnored(it)) {
      return false;
    }
    if (filter === "all" && hideIgnored && isIgnored(it)) {
      return false;
    }
    if (!q) {
      return true;
    }
    const h = itemInfo(it);
    return normKey(
      [
        it.payer_nom,
        it.payer_prenom,
        h.beneficiary,
        h.payerName,
        h.payerEmail,
        h.orderId,
        it.id_item,
        it.licence_saisie,
        it.competition_saisie,
        h.itemName,
        h.formName,
        it.commentaire,
        it.ignore_motif,
        compName.get(it.competition_id ?? -1),
        member.get(it.adherent_id ?? -1),
        ...h.fields.map((f) => f.answer),
      ]
        .filter((v) => v != null)
        .join(" "),
    ).includes(q);
  });
  const rank = (it: HelloAssoItem) => (isLinked(it) ? 1 : isIgnored(it) ? 2 : 0);
  const dates = new Map(shown.map((it) => [it, itemInfo(it).date]));
  return shown.sort((a, b) => rank(a) - rank(b) || (dates.get(b) ?? "").localeCompare(dates.get(a) ?? ""));
}

/** The competition an item is for: its link, else the one whose FFME number or name the payer typed. */
export function suggestedCompetition(it: HelloAssoItem, competitions: readonly Competition[]): number | null {
  if (it.competition_id != null && competitions.some((c) => c.id === it.competition_id)) {
    return it.competition_id;
  }
  const typed = normKey([it.competition_saisie, ...itemInfo(it).fields.map((f) => f.answer)].join(" "));
  if (!typed) {
    return null;
  }
  const match = sortCompetitions(competitions).find((c) => {
    const number = normKey(c.id_ffme);
    const name = normKey(c.nom);
    return (number && typed.includes(number)) || (name && typed.includes(name));
  });
  return match?.id ?? null;
}

const digits = (s: string | null | undefined) => (s ?? "").replace(/\D/g, "");

/** The member an item is for: its link, else the licence number typed, else the beneficiary's name. */
export function suggestedMember(it: HelloAssoItem, members: readonly MemberSlot[]): number | null {
  if (it.adherent_id != null && members.some((m) => m.id === it.adherent_id)) {
    return it.adherent_id;
  }
  const info = itemInfo(it);
  const licences = [it.licence_saisie, ...info.fields.map((f) => f.answer)].map(digits).filter((d) => d.length >= 5);
  const byLicence = members.find((m) => digits(m.licence_ffme) && licences.includes(digits(m.licence_ffme)));
  if (byLicence) {
    return byLicence.id ?? null;
  }
  const name = normKey(`${info.beneficiary} ${it.payer_nom ?? ""} ${it.payer_prenom ?? ""}`);
  const byName = members.find(
    (m) => normKey(m.nom) && name.includes(normKey(m.nom)) && (!normKey(m.prenom) || name.includes(normKey(m.prenom))),
  );
  return byName?.id ?? null;
}

export function syncMessage(answer: Schemas["HelloAssoSync"]): string {
  if (answer.status !== "success") {
    return `❌ ${answer.message || "Erreur lors de la synchronisation."}`;
  }
  const st = answer.stats;
  return `✅ Synchro terminée : ${st?.nb_items ?? 0} article(s), ${st?.nb_auto ?? 0} auto, ${st?.nb_unlinked ?? 0} en attente.`;
}
