import { describe, expect, it } from "vitest";
import { ref } from "vue";
import type { Competition } from "../competitions";
import { useCompetitionFilters } from "./filters";

const TODAY = "2026-11-16";
const LIST: Competition[] = [
  { id: 1, nom: "Coupe de Lyon", date_competition: "2026-12-05", participants: [] },
  { id: 2, nom: "Open de Grenoble", date_competition: "2026-10-03", participants: [] },
  { id: 3, nom: "Championnat 2025", date_competition: "2025-03-01", statut: "close", participants: [] },
  { id: 4, nom: "Sans date", participants: [] },
  { id: 5, nom: "Régional", date_competition: "2026-05-10", participants: [] },
];
const ids = (list: readonly Competition[]): number[] => list.map((c) => c.id);

describe("useCompetitionFilters", () => {
  it("shows every season, undated ones included, and lists the seasons newest first", () => {
    const filters = useCompetitionFilters(ref(LIST), TODAY);
    expect(filters.seasons.value).toEqual(["2026-2027", "2025-2026", "2024-2025"]);
    expect(ids(filters.current.value)).toEqual([1, 2, 4, 5]);
    expect(ids(filters.archived.value)).toEqual([3]);
    expect(filters.filtered.value).toBe(false);
  });

  it("keeps the competitions of the season chosen, undated ones hidden then", () => {
    const filters = useCompetitionFilters(ref(LIST), TODAY);
    filters.selectedSeason.value = "2025-2026";
    expect(ids(filters.current.value)).toEqual([5]);
    expect(filters.filtered.value).toBe(true);
  });

  it("applies the search and the date chips to the current and archived lists, the search only to the calendar", () => {
    const filters = useCompetitionFilters(ref(LIST), TODAY);
    filters.when.value = "upcoming";
    expect(ids(filters.current.value)).toEqual([1, 4]);
    filters.when.value = "past";
    expect(ids(filters.current.value)).toEqual([2, 5]);
    expect(ids(filters.archived.value)).toEqual([3]);
    expect(ids(filters.calendar.value)).toEqual([1, 2, 3, 4, 5]);
    filters.search.value = "grenoble";
    expect(ids(filters.current.value)).toEqual([2]);
    expect(ids(filters.calendar.value)).toEqual([2]);
    expect(filters.filtered.value).toBe(true);
  });

  it("lists the competitions over and not archived, whatever the filters, and follows the list", () => {
    const all = ref(LIST);
    const filters = useCompetitionFilters(all, TODAY);
    filters.search.value = "lyon";
    expect(ids(filters.past.value)).toEqual([2, 5]);
    all.value = [...LIST, { id: 6, nom: "Hier", date_competition: "2026-11-15", participants: [] }];
    expect(ids(filters.past.value)).toEqual([2, 5, 6]);
  });
});
