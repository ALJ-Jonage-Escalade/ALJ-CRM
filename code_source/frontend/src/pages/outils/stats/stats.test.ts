import { describe, expect, it } from "vitest";
import type { Competition, Participant } from "../../competitions/competitions";
import { competitionsPerMonth, seasonParticipation, seasonPodiums } from "./stats";

const entrant = (adherentId: number, change: Partial<Participant> = {}): Participant => ({
  adherent_id: adherentId,
  nom: "N",
  prenom: "P",
  selectionne: true,
  ...change,
});
const competition = (id: number, date: string | undefined, participants: Participant[]): Competition => ({
  id,
  nom: `C${id}`,
  date_competition: date,
  participants,
});

const LIST = [
  competition(1, "2026-10-04", [entrant(1, { classement: "1", present: true }), entrant(2, { classement: "4", present: true })]),
  competition(2, "2027-03-14", [entrant(1, { classement: "3" }), entrant(3, { classement: "2", present: true })]),
  competition(3, "2025-11-20", [entrant(1, { classement: "1", present: true }), entrant(4, { selectionne: false, classement: "2" })]),
  competition(4, undefined, [entrant(9, { classement: "1" })]),
];

describe("stats", () => {
  it("counts the podiums per season, most recent first, undated competitions left out", () => {
    expect(seasonPodiums(LIST)).toEqual([
      { season: "2026-2027", podiums: 3 },
      { season: "2025-2026", podiums: 2 },
    ]);
    expect(seasonPodiums(LIST, 1).map((s) => s.season)).toEqual(["2026-2027"]);
  });

  it("counts every competition of the season, undated ones in the current season, their selected competitors and the distinct members among them", () => {
    const list = [
      ...LIST,
      competition(5, "2026-12-01", [entrant(2, { selectionne: false })]), // nobody selected
      competition(6, "2027-05-01", [entrant(1), entrant(2)]), // upcoming
    ];

    expect(seasonParticipation(list, "2027-04-01")).toEqual({ competitions: 5, competitors: 7, uniqueCompetitors: 4 });
    expect(seasonParticipation(list, "2028-01-01")).toEqual({ competitions: 1, competitors: 1, uniqueCompetitors: 1 });
  });

  it("counts the season's competitions per month, September to August, undated ones left out", () => {
    const perMonth = competitionsPerMonth([...LIST, competition(5, "2027-08-30", []), competition(6, "2026-10-20", [])], "2026-11-23");

    expect(perMonth.map((m) => m.month)).toEqual([
      "Sept.",
      "Oct.",
      "Nov.",
      "Déc.",
      "Janv.",
      "Févr.",
      "Mars",
      "Avr.",
      "Mai",
      "Juin",
      "Juil.",
      "Août",
    ]);
    expect(perMonth.map((m) => m.competitions)).toEqual([0, 2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
  });
});
