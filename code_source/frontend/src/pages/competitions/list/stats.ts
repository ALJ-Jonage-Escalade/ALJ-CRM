/* The figures shown when no competition is opened. */
import { isPast, type Competition } from "../competitions";

export interface CompetitionStats {
  competitions: number;
  upcoming: number;
  past: number;
  /** Distinct competitors: by member id, else by name */
  competitors: number;
  participations: number;
  /** Price × selected participants (every participant when none is selected yet) */
  budget: number;
  paid: number;
}

export function competitionStats(competitions: readonly Competition[], today: string): CompetitionStats {
  const competitors = new Set<string>();
  let participations = 0;
  let budget = 0;
  let paid = 0;
  for (const competition of competitions) {
    const participants = competition.participants ?? [];
    participations += participants.length;
    for (const p of participants) {
      const key =
        p.adherent_id != null ? String(p.adherent_id) : `${(p.nom ?? "").trim().toLowerCase()}_${(p.prenom ?? "").trim().toLowerCase()}`;
      if (key !== "_") {
        competitors.add(key);
      }
      paid += Number(p.montant_paye ?? 0);
    }
    const price = Number(competition.prix ?? 0);
    if (price) {
      const selectedCount = participants.filter((p) => p.selectionne).length;
      budget += price * (selectedCount > 0 ? selectedCount : participants.length);
    }
  }
  const upcoming = competitions.filter((c) => !isPast(c, today)).length;
  return {
    competitions: competitions.length,
    upcoming,
    past: competitions.length - upcoming,
    competitors: competitors.size,
    participations,
    budget,
    paid,
  };
}
