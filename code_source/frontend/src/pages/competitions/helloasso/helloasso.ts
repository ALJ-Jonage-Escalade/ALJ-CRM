/* HelloAsso payments of the competitions (« HelloAsso »): the items of the annual campaign (GET /api/helloasso/items,
   mirrored by POST /api/helloasso/sync), linked to a participant automatically or by a coach, or ignored. Port of the
   former phone page's HelloAsso tab. HelloAsso custom fields carry the answer in `answer` or `value`: both are read. */
import type { Schemas } from "../../../lib/client";
import { plural } from "../../../lib/text";
import { normKey } from "../../../lib/text";
import { sortCompetitions, type Competition, type MemberSlot } from "../competitions";

export type HelloAssoItem = Schemas["HelloAssoItem"];

export const isLinked = (item: HelloAssoItem): boolean => item.competition_id != null && item.adherent_id != null;
/** Set aside by a coach (test, purchase unrelated to a competition…). */
export const isIgnored = (item: HelloAssoItem): boolean => item.ignore === true && !isLinked(item);

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

function parseRaw(item: HelloAssoItem): Raw {
  try {
    return obj(item.raw_json ? JSON.parse(item.raw_json) : null);
  } catch {
    return {};
  }
}

/** Everything known of an item: the mirror's fields, completed by HelloAsso's raw item. */
export function itemInfo(item: HelloAssoItem): ItemInfo {
  const rawItem = parseRaw(item);
  const order = obj(rawItem.order);
  const payer = obj(rawItem.payer);
  const payments = list(rawItem.payments).map(obj);
  return {
    beneficiary: fullName(obj(rawItem.user)) || `${item.payer_prenom ?? ""} ${item.payer_nom ?? ""}`.trim(),
    payerName: fullName(payer),
    payerEmail: text(payer.email),
    payerCity: [payer.zipCode, payer.city].filter(Boolean).map(text).join(" "),
    orderId: text(item.order_id ?? order.id),
    date: item.date_item || text(order.date) || text(payments[0]?.date),
    formName: text(order.formName || order.formSlug || item.campagne_slug),
    itemName: text(rawItem.name),
    state: item.etat || text(rawItem.state),
    amount: Number(item.montant ?? 0),
    initialAmount: cents(rawItem.initialAmount),
    payments: payments.map((payment) => ({
      id: text(payment.id),
      amount: cents(payment.amount ?? payment.shareAmount),
      state: text(payment.state),
      date: text(payment.date),
      means: text(payment.paymentMeans),
    })),
    fields: fields(rawItem.customFields),
    options: list(rawItem.options)
      .map(obj)
      .map((o) => ({ name: text(o.name), amount: cents(o.amount), fields: fields(o.customFields) })),
    raw: rawItem,
  };
}

export function displayName(item: HelloAssoItem, info: ItemInfo = itemInfo(item)): string {
  return info.beneficiary || info.payerName || `Article #${item.id_item}`;
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
  const wanted = normKey(search);
  const compName = new Map(competitions.map((c) => [c.id, c.nom ?? ""]));
  const member = new Map(members.map((m) => [m.id, `${m.nom} ${m.prenom}`]));
  const shown = items.filter((item) => {
    if (filter === "unlinked" && (isLinked(item) || isIgnored(item))) {
      return false;
    }
    if (filter === "linked" && !isLinked(item)) {
      return false;
    }
    if (filter === "ignored" && !isIgnored(item)) {
      return false;
    }
    if (filter === "all" && hideIgnored && isIgnored(item)) {
      return false;
    }
    if (!wanted) {
      return true;
    }
    const info = itemInfo(item);
    return normKey(
      [
        item.payer_nom,
        item.payer_prenom,
        info.beneficiary,
        info.payerName,
        info.payerEmail,
        info.orderId,
        item.id_item,
        item.licence_saisie,
        item.competition_saisie,
        info.itemName,
        info.formName,
        item.commentaire,
        item.ignore_motif,
        compName.get(item.competition_id ?? -1),
        member.get(item.adherent_id ?? -1),
        ...info.fields.map((f) => f.answer),
      ]
        .filter((v) => v != null)
        .join(" "),
    ).includes(wanted);
  });
  const rank = (it: HelloAssoItem) => (isLinked(it) ? 1 : isIgnored(it) ? 2 : 0);
  const dates = new Map(shown.map((it) => [it, itemInfo(it).date]));
  return shown.sort((a, b) => rank(a) - rank(b) || (dates.get(b) ?? "").localeCompare(dates.get(a) ?? ""));
}

const isPending = (item: HelloAssoItem): boolean => !isLinked(item) && !isIgnored(item);

/** The items of a linking pass (« Rattacher les paiements en attente »): the pending ones of the list shown, in its order. */
export function pendingIds(shown: readonly HelloAssoItem[]): number[] {
  return shown.filter(isPending).map((it) => it.id_item);
}

/** Position in `ids` of the next item still pending after `after` (a sync may have linked some meanwhile), -1 at the end
    of the pass. Only the items after `after` count: one saved without being linked stays behind. */
export function nextPending(ids: readonly number[], after: number, items: readonly HelloAssoItem[]): number {
  const byId = new Map(items.map((it) => [it.id_item, it]));
  return ids.findIndex((id, position) => {
    const item = byId.get(id);
    return position > after && item != null && isPending(item);
  });
}

export interface PassTally {
  linked: number;
  /** saved with a competition or a member only: still pending */
  saved: number;
  ignored: number;
  skipped: number;
}

/** What a linking pass did, for the toast closing it; empty when nothing was done. */
export function passSummary(tally: PassTally): string {
  return [
    tally.linked && `✅ ${tally.linked} rattaché${plural(tally.linked)}`,
    tally.saved && `💾 ${tally.saved} enregistré${plural(tally.saved)} sans rattachement`,
    tally.ignored && `🚫 ${tally.ignored} ignoré${plural(tally.ignored)}`,
    tally.skipped && `⏭ ${tally.skipped} passé${plural(tally.skipped)}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** The competition an item is for: its link, else the one whose FFME number or name the payer typed. */
export function suggestedCompetition(item: HelloAssoItem, competitions: readonly Competition[]): number | null {
  if (item.competition_id != null && competitions.some((c) => c.id === item.competition_id)) {
    return item.competition_id;
  }
  const typed = normKey([item.competition_saisie, ...itemInfo(item).fields.map((f) => f.answer)].join(" "));
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
export function suggestedMember(item: HelloAssoItem, members: readonly MemberSlot[]): number | null {
  if (item.adherent_id != null && members.some((m) => m.id === item.adherent_id)) {
    return item.adherent_id;
  }
  const info = itemInfo(item);
  const licences = [item.licence_saisie, ...info.fields.map((f) => f.answer)].map(digits).filter((d) => d.length >= 5);
  const byLicence = members.find((m) => digits(m.licence_ffme) && licences.includes(digits(m.licence_ffme)));
  if (byLicence) {
    return byLicence.id ?? null;
  }
  const name = normKey(`${info.beneficiary} ${item.payer_nom ?? ""} ${item.payer_prenom ?? ""}`);
  const byName = members.find(
    (m) => normKey(m.nom) && name.includes(normKey(m.nom)) && (!normKey(m.prenom) || name.includes(normKey(m.prenom))),
  );
  return byName?.id ?? null;
}

export function syncMessage(answer: Schemas["HelloAssoSync"]): string {
  // A failure (no campaign, HelloAsso unreachable) is an HTTP error: shown by the writer, never reaches here
  const stats = answer.stats;
  return `✅ Synchro terminée : ${stats.nb_items} article(s), ${stats.nb_auto} auto, ${stats.nb_unlinked} en attente.`;
}
