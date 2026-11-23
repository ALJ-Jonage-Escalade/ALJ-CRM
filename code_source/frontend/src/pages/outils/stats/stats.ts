/* Statistics of the competitions (Outils › Statistiques), computed from the competitions the server returns: podiums
   per season, competitions and competitors of the current season. Nothing is shown that the data does not hold. */
import { seasonOf, todayIso, type Competition } from "../../competitions/competitions";

export interface SeasonPodiums {
  season: string;
  /** Competitors ranked 1st, 2nd or 3rd (one per participation) */
  podiums: number;
}

/** The seasons with dated competitions, most recent first, `limit` at most. */
export function seasonPodiums(competitions: readonly Competition[], limit = 3): SeasonPodiums[] {
  const podiumsBySeason = new Map<string, number>();
  for (const competition of competitions) {
    const season = seasonOf(competition.date_competition);
    if (!season) {
      continue;
    }
    const podiums = (competition.participants ?? []).filter((participant) =>
      ["1", "2", "3"].includes(String(participant.classement ?? "").trim()),
    ).length;
    podiumsBySeason.set(season, (podiumsBySeason.get(season) ?? 0) + podiums);
  }
  return [...podiumsBySeason.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .slice(0, limit)
    .map(([season, podiums]) => ({ season, podiums }));
}

/** The club's competitions in the season of `today` (YYYY-MM-DD): past and upcoming, archived or not. An undated
    competition belongs to the current season, as in Compétitions › Bilan. */
export interface SeasonParticipation {
  competitions: number;
  /** Selected competitors added over these competitions (a member in two competitions counts twice) */
  competitors: number;
  /** Distinct members selected for at least one of these competitions */
  uniqueCompetitors: number;
}

export function seasonParticipation(competitions: readonly Competition[], today: string = todayIso()): SeasonParticipation {
  const season = seasonOf(today);
  const seasonCompetitions = competitions.filter((competition) => (seasonOf(competition.date_competition) || season) === season);
  const selected = seasonCompetitions.flatMap((competition) =>
    (competition.participants ?? []).filter((participant) => participant.selectionne),
  );
  return {
    competitions: seasonCompetitions.length,
    competitors: selected.length,
    uniqueCompetitors: new Set(selected.flatMap((participant) => participant.adherent_id ?? [])).size,
  };
}

/** The months of a season, September to August. */
const SEASON_MONTHS = ["Sept.", "Oct.", "Nov.", "Déc.", "Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août"] as const;

export interface MonthCount {
  month: string;
  competitions: number;
}

/** The competitions of the season of `today` per month of their start date, September to August; undated ones are left out. */
export function competitionsPerMonth(competitions: readonly Competition[], today: string = todayIso()): MonthCount[] {
  const season = seasonOf(today);
  const counts = SEASON_MONTHS.map(() => 0);
  for (const competition of competitions) {
    const date = competition.date_competition ?? "";
    if (seasonOf(date) === season) {
      const monthIndex = (Number(date.slice(5, 7)) + 3) % 12; // September (9) → 0, August (8) → 11
      counts[monthIndex] = (counts[monthIndex] ?? 0) + 1;
    }
  }
  return SEASON_MONTHS.map((month, index) => ({ month, competitions: counts[index] ?? 0 }));
}
