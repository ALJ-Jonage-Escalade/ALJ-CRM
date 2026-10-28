import { describe, expect, it } from "vitest";
import type { Competition, Participant } from "../competitions";
import { competitionStats } from "./stats";

const comp = (id: number, date: string, participants: Partial<Participant>[], prix?: number): Competition => ({
  id,
  nom: `C${id}`,
  date_competition: date,
  statut: "en_preparation",
  prix,
  participants: participants.map((p) => ({ nom: "", prenom: "", ...p })),
});

describe("competitionStats", () => {
  it("counts the competitions, the distinct competitors and the money", () => {
    const stats = competitionStats(
      [
        comp(1, "2026-10-01", [{ adherent_id: 1, selectionne: true, montant_paye: 10 }, { adherent_id: 2 }], 10),
        comp(
          2,
          "2026-11-15",
          [
            { adherent_id: 1, montant_paye: 5 },
            { nom: "Potter", prenom: "Harry" },
          ],
          5,
        ),
        comp(3, "2026-12-01", [{ nom: " potter", prenom: "HARRY " }]),
      ],
      "2026-10-28",
    );
    expect(stats).toEqual({ competitions: 3, upcoming: 2, past: 1, competitors: 3, participations: 5, budget: 20, paid: 15 });
  });

  it("is all zeros without competitions", () => {
    expect(competitionStats([], "2026-10-28")).toEqual({
      competitions: 0,
      upcoming: 0,
      past: 0,
      competitors: 0,
      participations: 0,
      budget: 0,
      paid: 0,
    });
  });
});
