import { describe, expect, it } from "vitest";
import type { Competition, Participant } from "../../competitions/competitions";
import { participationRateText, seasonParticipation, seasonStats } from "./stats";

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
  it("counts podiums and selected competitors per season, most recent first, undated competitions left out", () => {
    expect(seasonStats(LIST)).toEqual([
      { season: "2026-2027", gold: 1, silver: 1, bronze: 1, podiums: 3, competitors: 3 },
      { season: "2025-2026", gold: 1, silver: 1, bronze: 0, podiums: 2, competitors: 1 },
    ]);
    expect(seasonStats(LIST, 1).map((s) => s.season)).toEqual(["2026-2027"]);
  });

  it("rates the presence of the selected competitors, a dash without any", () => {
    expect(participationRateText(LIST)).toBe("67 %");
    expect(participationRateText([])).toBe("—");
  });

  it("counts the competitions of the season the club took part in so far, and their selected competitors", () => {
    const list = [
      ...LIST,
      competition(5, "2026-12-01", [entrant(2, { selectionne: false })]), // nobody selected
      competition(6, "2027-05-01", [entrant(1), entrant(2)]), // still to come
    ];

    expect(seasonParticipation(list, "2027-04-01")).toEqual({ competitions: 2, competitors: 4 });
    expect(seasonParticipation(list, "2028-01-01")).toEqual({ competitions: 0, competitors: 0 });
  });
});
