/* Season balance of the competitors (« Bilan »): what each one owes for the competitions they were selected for, and
   what they paid. Merges the balances of the former phone and office pages, with one rule set:
   - selected: the competition's price is due, the amount paid counts;
   - cancelled, money carried over (annule_reporte): nothing due, the amount paid stays as a credit;
   - cancelled, money lost (annule_perdu): kept by the club, neither due nor credit (shown, balanced);
   - neither selected nor paid: not counted.
   A season runs from August to July. */
import type { Cell } from "../../lib/csv";
import { formatEuros } from "../../lib/format";
import { normKey } from "../adherents/members";
import { isPast, ranking, todayIso, type Competition, type Participant } from "./competitions";

/** « 2026-2027 » for a date from August 2026 to July 2027. */
export function seasonOf(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  const start = (m ?? 1) >= 8 ? y! : y! - 1;
  return `${start}-${start + 1}`;
}

/** Seasons with competitions, and the current one; most recent first. Undated competitions count in the current one. */
export function seasons(list: readonly Competition[], today: string = todayIso()): string[] {
  const all = new Set([seasonOf(today), ...list.filter((c) => c.date_competition).map((c) => seasonOf(c.date_competition!))]);
  return [...all].sort().reverse();
}

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

function line(c: Competition, p: Participant, today: string): BalanceLine | null {
  const status = p.statut_paiement || "non_invite";
  const paid = Number(p.montant_paye ?? 0);
  const absent = isPast(c, today) && paid > 0 && status === "paye" && !p.present;
  const base = { competition: c, participant: p, status, present: !!p.present, absent, ranking: ranking(p) };
  if (status === "annule_reporte") {
    return { ...base, due: 0, paid, carriedOver: true };
  }
  if (status === "annule_perdu") {
    return { ...base, due: paid, paid, carriedOver: false };
  }
  if (!p.selectionne && !paid) {
    return null;
  }
  return { ...base, due: p.selectionne ? Number(c.prix ?? 0) : 0, paid, carriedOver: false };
}

const round = (n: number) => Math.round(n * 100) / 100;

/** The competitors of the season's competitions, by name. */
export function balances(list: readonly Competition[], season: string, today: string = todayIso()): Balance[] {
  const current = seasonOf(today);
  const byMember = new Map<string, Balance>();
  for (const c of list) {
    if ((c.date_competition ? seasonOf(c.date_competition) : current) !== season) {
      continue;
    }
    for (const p of c.participants ?? []) {
      const l = line(c, p, today);
      if (!l) {
        continue;
      }
      const key = p.adherent_id != null ? String(p.adherent_id) : `${p.nom}|${p.prenom}`;
      const b = byMember.get(key) ?? {
        adherentId: p.adherent_id ?? null,
        nom: (p.nom ?? "").toUpperCase(),
        prenom: p.prenom ?? "",
        licence: p.num_licence ?? "",
        email: "",
        phone: "",
        group: "",
        lines: [],
        due: 0,
        paid: 0,
        remaining: 0,
        absent: false,
      };
      b.lines.push(l);
      b.due = round(b.due + l.due);
      b.paid = round(b.paid + l.paid);
      b.remaining = round(b.due - b.paid);
      b.absent ||= l.absent;
      byMember.set(key, b);
    }
  }
  for (const b of byMember.values()) {
    b.lines.sort((x, y) => (x.competition.date_competition ?? "").localeCompare(y.competition.date_competition ?? ""));
    const latest = (field: "email" | "phone" | "tarif") =>
      b.lines.map((l) => l.participant[field]?.trim() ?? "").reduce((found, value) => value || found, "");
    b.email = latest("email");
    b.phone = latest("phone");
    b.group = latest("tarif");
  }
  return [...byMember.values()].sort((a, b) => a.nom.localeCompare(b.nom, "fr") || a.prenom.localeCompare(b.prenom, "fr"));
}

export function searchBalances(list: readonly Balance[], search: string): Balance[] {
  const q = normKey(search);
  return q
    ? list.filter(
        (b) => normKey(`${b.nom} ${b.prenom}`).includes(q) || normKey(`${b.prenom} ${b.nom}`).includes(q) || normKey(b.licence).includes(q),
      )
    : list.slice();
}

export function totals(list: readonly Balance[]): { due: number; paid: number; remaining: number } {
  const due = round(list.reduce((n, b) => n + b.due, 0));
  const paid = round(list.reduce((n, b) => n + b.paid, 0));
  return { due, paid, remaining: round(due - paid) };
}

/** « ✅ Équilibré », « ⚠️ Reste dû 15,00 € » or « Crédit 12,00 € ». */
export function balanceLabel(b: Pick<Balance, "remaining">): { text: string; tone: "ok" | "due" | "credit" } {
  if (b.remaining > 0.005) {
    return { text: `⚠️ Reste dû ${formatEuros(b.remaining)}`, tone: "due" };
  }
  if (b.remaining < -0.005) {
    return { text: `💜 Crédit ${formatEuros(-b.remaining)}`, tone: "credit" };
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
