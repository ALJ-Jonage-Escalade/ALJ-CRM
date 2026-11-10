/* Statistics of the competitions (Outils › Statistiques), computed from the competitions the server returns: podiums
   and competitors per season, presence of the selected competitors. Nothing is shown that the data does not hold. */
import { seasonOf, type Competition } from "../competitions/competitions";

/** The medal counted for a podium rank. */
const MEDAL_OF_RANK = { 1: "gold", 2: "silver", 3: "bronze" } as const;

export interface SeasonStats {
  season: string;
  /** Competitors ranked 1st, 2nd or 3rd (one per participation) */
  gold: number;
  silver: number;
  bronze: number;
  podiums: number;
  /** Members selected for at least one competition of the season */
  competitors: number;
}

/** The seasons with dated competitions, most recent first, `limit` at most. */
export function seasonStats(competitions: readonly Competition[], limit = 3): SeasonStats[] {
  const bySeason = new Map<string, { gold: number; silver: number; bronze: number; competitors: Set<number> }>();
  for (const competition of competitions) {
    const season = seasonOf(competition.date_competition);
    if (!season) {
      continue;
    }
    const entry = bySeason.get(season) ?? { gold: 0, silver: 0, bronze: 0, competitors: new Set<number>() };
    bySeason.set(season, entry);
    for (const participant of competition.participants ?? []) {
      const rank = Number(String(participant.classement ?? "").trim());
      if (rank === 1 || rank === 2 || rank === 3) {
        entry[MEDAL_OF_RANK[rank]] += 1;
      }
      if (participant.selectionne && participant.adherent_id != null) {
        entry.competitors.add(participant.adherent_id);
      }
    }
  }
  return [...bySeason.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .slice(0, limit)
    .map(([season, { gold, silver, bronze, competitors }]) => ({
      season,
      gold,
      silver,
      bronze,
      podiums: gold + silver + bronze,
      competitors: competitors.size,
    }));
}

/** « 75 % » of the selected competitors marked present, « — » when nobody was selected. */
export function participationRateText(competitions: readonly Competition[]): string {
  const selected = competitions.flatMap((competition) => (competition.participants ?? []).filter((participant) => participant.selectionne));
  if (!selected.length) {
    return "—";
  }
  const present = selected.filter((participant) => participant.present).length;
  return `${Math.round((present / selected.length) * 100)} %`;
}

/** « +63 % » from the oldest to the most recent of the seasons (most recent first), « — » without two seasons to compare. */
export function competitorGrowthText(seasons: readonly SeasonStats[]): string {
  const latest = seasons[0];
  const oldest = seasons[seasons.length - 1];
  if (!latest || !oldest || latest === oldest || !oldest.competitors) {
    return "—";
  }
  const growth = Math.round(((latest.competitors - oldest.competitors) / oldest.competitors) * 100);
  return `${growth > 0 ? "+" : ""}${growth} %`;
}
