/* Season balance of the competitors (« Bilan »): what each one owes for the competitions they were selected for, and
   what they paid. Merges the balances of the former phone and office pages, with one rule set:
   - selected: the competition's price is due, the amount paid counts;
   - cancelled, money carried over (annule_reporte): nothing due, the amount paid stays as a credit;
   - cancelled, money lost (annule_perdu): kept by the club, neither due nor credit (shown, balanced);
   - neither selected nor paid: not counted.
   A season runs from September to August (seasonOf). */
import type { Cell } from "../../../lib/csv";
import { formatEuros } from "../../../lib/format";
import { normKey } from "../../../lib/text";
import { isPast, rankingText, seasonOf, todayIso, type Competition, type Participant } from "../competitions";

export interface BalanceLine {
  competition: Competition;
  /** The competitor's entry in it: HelloAsso order, FFME category, contact details… */
  participant: Participant;
  due: number;
  paid: number;
  status: string;
  present: boolean;
  carriedOver: boolean;
  /** Paid for a competition that is over without being checked in. */
  absent: boolean;
  /** « 🥇 1er », « 🏅 4 / 23 »… once the results are in, empty before. */
  ranking: string;
}

export interface Balance {
  adherentId: number | null;
  nom: string;
  prenom: string;
  licence: string;
  /** Contact details and tariff (« Catégorie / Groupe ») of their most recent entry that has them. */
  email: string;
  phone: string;
  group: string;
  lines: BalanceLine[];
  due: number;
  paid: number;
  /** Still to pay (> 0), or credit (< 0). */
  remaining: number;
  /** Absent from at least one of their lines. */
  absent: boolean;
}

/** The competitor's line for one competition, null when it does not count (neither selected nor paid). */
function line(competition: Competition, participant: Participant, today: string): BalanceLine | null {
  const status = participant.statut_paiement || "non_invite";
  const paid = Number(participant.montant_paye ?? 0);
  const absent = isPast(competition, today) && paid > 0 && status === "paye" && !participant.present;
  const base = { competition, participant, status, present: !!participant.present, absent, ranking: rankingText(participant) };
  if (status === "annule_reporte") {
    return { ...base, due: 0, paid, carriedOver: true };
  }
  if (status === "annule_perdu") {
    return { ...base, due: paid, paid, carriedOver: false };
  }
  if (!participant.selectionne && !paid) {
    return null;
  }
  return { ...base, due: participant.selectionne ? Number(competition.prix ?? 0) : 0, paid, carriedOver: false };
}

const round = (amount: number): number => Math.round(amount * 100) / 100;

/** A competitor's balance before their first line; contact details are filled from the lines at the end. */
function emptyBalance(participant: Participant): Balance {
  return {
    adherentId: participant.adherent_id ?? null,
    nom: (participant.nom ?? "").toUpperCase(),
    prenom: participant.prenom ?? "",
    licence: participant.num_licence ?? "",
    email: "",
    phone: "",
    group: "",
    lines: [],
    due: 0,
    paid: 0,
    remaining: 0,
    absent: false,
  };
}

/** The value of the most recent line that has one (lines sorted by date). */
function latest(balance: Balance, field: "email" | "phone" | "tarif"): string {
  return balance.lines.map((entry) => entry.participant[field]?.trim() ?? "").reduce((found, value) => value || found, "");
}

/** The competitors of the season's competitions, by name. */
export function balances(list: readonly Competition[], season: string, today: string = todayIso()): Balance[] {
  const current = seasonOf(today);
  const byMember = new Map<string, Balance>();
  for (const competition of list) {
    if ((seasonOf(competition.date_competition) || current) !== season) {
      continue;
    }
    for (const participant of competition.participants ?? []) {
      const entry = line(competition, participant, today);
      if (!entry) {
        continue;
      }
      const key = participant.adherent_id != null ? String(participant.adherent_id) : `${participant.nom}|${participant.prenom}`;
      const balance = byMember.get(key) ?? emptyBalance(participant);
      balance.lines.push(entry);
      balance.due = round(balance.due + entry.due);
      balance.paid = round(balance.paid + entry.paid);
      balance.remaining = round(balance.due - balance.paid);
      balance.absent ||= entry.absent;
      byMember.set(key, balance);
    }
  }
  for (const balance of byMember.values()) {
    balance.lines.sort((x, y) => (x.competition.date_competition ?? "").localeCompare(y.competition.date_competition ?? ""));
    balance.email = latest(balance, "email");
    balance.phone = latest(balance, "phone");
    balance.group = latest(balance, "tarif");
  }
  return [...byMember.values()].sort((a, b) => a.nom.localeCompare(b.nom, "fr") || a.prenom.localeCompare(b.prenom, "fr"));
}

export function searchBalances(list: readonly Balance[], search: string): Balance[] {
  const wanted = normKey(search);
  return wanted
    ? list.filter(
        (b) =>
          normKey(`${b.nom} ${b.prenom}`).includes(wanted) ||
          normKey(`${b.prenom} ${b.nom}`).includes(wanted) ||
          normKey(b.licence).includes(wanted),
      )
    : list.slice();
}

export function totals(list: readonly Balance[]): { due: number; paid: number; remaining: number } {
  const due = round(list.reduce((n, b) => n + b.due, 0));
  const paid = round(list.reduce((n, b) => n + b.paid, 0));
  return { due, paid, remaining: round(due - paid) };
}

/** « ✅ Équilibré », « ⚠️ Reste dû 15,00 € » or « Crédit 12,00 € ». */
export function balanceLabel(balance: Pick<Balance, "remaining">): { text: string; tone: "ok" | "due" | "credit" } {
  if (balance.remaining > 0.005) {
    return { text: `⚠️ Reste dû ${formatEuros(balance.remaining)}`, tone: "due" };
  }
  if (balance.remaining < -0.005) {
    return { text: `💜 Crédit ${formatEuros(-balance.remaining)}`, tone: "credit" };
  }
  return { text: "✅ Équilibré", tone: "ok" };
}

export function balanceCsv(list: readonly Balance[]): Cell[][] {
  return [
    ["Nom", "Prénom", "N° Licence FFME", "Épreuves", "Total dû (€)", "Total payé (€)", "Reste dû (€)", "Remarques (reports / absences)"],
    ...list.map((b) => [
      b.nom,
      b.prenom,
      b.licence,
      b.lines.length,
      b.due.toFixed(2),
      b.paid.toFixed(2),
      b.remaining.toFixed(2),
      b.lines
        .filter((l) => l.carriedOver)
        .map((l) => `${l.competition.nom} : reporté`)
        .concat(b.absent ? ["Absent à une épreuve payée"] : [])
        .join(" | "),
    ]),
  ];
}
