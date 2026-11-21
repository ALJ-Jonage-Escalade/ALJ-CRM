import { describe, expect, it } from "vitest";
import type { MemberStatsRecord } from "./memberStats";
import { countBy, seasonMembers } from "./memberStats";

const SEASON = "2026-2027";

const purchase = (userId: number, change: Partial<MemberStatsRecord> = {}): MemberStatsRecord => ({
  user_id: userId,
  sex: "F",
  age: 30,
  age_band: "30 à 39 ans",
  city: "Jonage",
  group: "Adulte",
  status: "Validé",
  season: SEASON,
  returning: true,
  order_month: "2026-06",
  ...change,
});

describe("member stats", () => {
  it("counts each validated member of the season once, unknown sex as its own slice", () => {
    const records = [
      purchase(1, { sex: "F" }),
      purchase(1, { sex: "F", group: "Compétition" }),
      purchase(2, { sex: "H" }),
      purchase(3, { sex: null }),
      purchase(4, { sex: "H", status: "Annulé" }),
      purchase(5, { sex: "H", status: "Refusé" }),
      purchase(6, { sex: "H", season: "2025-2026" }),
    ];

    expect(countBy(seasonMembers(records, SEASON), "sex")).toEqual([
      { label: "Femmes", count: 1 },
      { label: "Hommes", count: 1 },
      { label: "Non renseigné", count: 1 },
    ]);
  });
});
