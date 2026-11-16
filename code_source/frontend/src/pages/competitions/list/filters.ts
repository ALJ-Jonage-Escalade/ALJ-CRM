/* The filters of the competition list (season, search, date chips) and the lists they give, shared by the cards, the
   table, the calendar and the statistics. */
import { computed, ref, type ComputedRef, type Ref } from "vue";
import { seasonOf, filterCompetitions, isArchived, isPast, type Competition, type When } from "../competitions";

export type ViewMode = "cards" | "table" | "calendar";

export interface CompetitionFilters {
  search: Ref<string>;
  when: Ref<When>;
  selectedSeason: Ref<string>;
  /** The seasons to choose from, the current one first even without a competition, newest first */
  seasons: ComputedRef<string[]>;
  /** The season ones matching the search and the date chips */
  current: ComputedRef<Competition[]>;
  archived: ComputedRef<Competition[]>;
  /** The search only, archived ones included: the calendar's months replace the season and date filters */
  calendar: ComputedRef<Competition[]>;
  /** Not archived and over, whatever the filters: those the "archive" button archives */
  past: ComputedRef<Competition[]>;
  /** A filter hides competitions */
  filtered: ComputedRef<boolean>;
}

export function useCompetitionFilters(all: Readonly<Ref<readonly Competition[]>>, today: string): CompetitionFilters {
  const search = ref("");
  const when = ref<When>("all");
  // Every season by default: a competition without a date (allowed) or of another season is never hidden unasked
  const selectedSeason = ref("all");

  const seasons = computed(() => {
    const set = new Set<string>([seasonOf(today)]);
    all.value.forEach((c) => {
      const season = seasonOf(c.date_competition);
      if (season) {
        set.add(season);
      }
    });
    return Array.from(set).sort().reverse();
  });

  const seasonCompetitions = computed(() => {
    const list = all.value.filter((c) => !isArchived(c));
    return selectedSeason.value === "all" ? list : list.filter((c) => seasonOf(c.date_competition) === selectedSeason.value);
  });
  const current = computed(() => filterCompetitions(seasonCompetitions.value, search.value, when.value, today));
  const archived = computed(() => filterCompetitions(all.value.filter(isArchived), search.value, when.value, today));
  const calendar = computed(() => filterCompetitions(all.value, search.value, "all", today));
  const past = computed(() => all.value.filter((c) => !isArchived(c) && isPast(c, today)));
  const filtered = computed(() => Boolean(search.value) || when.value !== "all" || selectedSeason.value !== "all");

  return { search, when, selectedSeason, seasons, current, archived, calendar, past, filtered };
}
