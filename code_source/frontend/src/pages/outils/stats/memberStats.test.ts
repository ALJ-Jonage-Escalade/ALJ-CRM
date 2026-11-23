import { describe, expect, it } from "vitest";
import type { MemberStatsRecord } from "./memberStats";
import { breakdown, countBy, memberCards, membersPerSeason, seasonMembers } from "./memberStats";

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

  it("breaks the genders down per group, a member counted in each group paid for, in counts or percentages", () => {
    const members = seasonMembers(
      [
        purchase(1, { sex: "F", group: "Adulte" }),
        purchase(1, { sex: "F", group: "Compétition" }),
        purchase(2, { sex: "H", group: "Adulte" }),
        purchase(3, { sex: "H", group: "Adulte" }),
        purchase(4, { sex: null, group: "Adulte" }),
      ],
      SEASON,
    );

    expect(breakdown(members, "sex", "group", "count")).toEqual({
      labels: ["Adulte", "Compétition"],
      series: [
        { label: "Femmes", values: [1, 1] },
        { label: "Hommes", values: [2, 0] },
        { label: "Non renseigné", values: [1, 0] },
      ],
    });
    expect(breakdown(members, "sex", "group", "percent").series.map((serie) => serie.values)).toEqual([
      [25, 100],
      [50, 0],
      [25, 0],
    ]);
  });

  it("orders the age bands by age, unknown ages last", () => {
    const members = seasonMembers(
      [
        purchase(1, { age_band: "65 ans et plus" }),
        purchase(2, { age_band: "Inconnue" }),
        purchase(3, { age_band: "10 à 17 ans" }),
        purchase(4, { age_band: "10 à 17 ans" }),
      ],
      SEASON,
    );

    expect(countBy(members, "ageBand")).toEqual([
      { label: "10 à 17 ans", count: 2 },
      { label: "65 ans et plus", count: 1 },
      { label: "Inconnue", count: 1 },
    ]);
  });

  it("keeps the 10 cities with the most members, the others merged in « Autres », also in a breakdown", () => {
    // City 0 has 12 members, city 1 has 11… city 11 has 1: cities 10 and 11 (2 + 1 members) go to « Autres »
    const records = Array.from({ length: 12 }, (_, city) =>
      Array.from({ length: 12 - city }, (_, index) => purchase(city * 100 + index, { city: `Ville ${city}`, sex: "H" })),
    ).flat();
    const members = seasonMembers(records, SEASON);

    const cities = countBy(members, "city");
    expect(cities.map((slice) => slice.label)).toEqual([...Array.from({ length: 10 }, (_, city) => `Ville ${city}`), "Autres"]);
    expect(cities.at(-1)).toEqual({ label: "Autres", count: 3 });
    expect(breakdown(members, "sex", "city", "count").labels.at(-1)).toBe("Autres");
    expect(breakdown(members, "sex", "city", "count").series[0]!.values.at(-1)).toBe(3);
  });

  it("splits the registrations of each month, in date order, between new and returning members", () => {
    const members = seasonMembers(
      [
        purchase(1, { order_month: "2026-09", returning: false }),
        purchase(2, { order_month: "2026-06", returning: true }),
        purchase(3, { order_month: "2026-09", returning: true }),
        purchase(4, { order_month: "Inconnue", returning: false }),
      ],
      SEASON,
    );

    expect(breakdown(members, "returning", "orderMonth", "count")).toEqual({
      labels: ["2026-06", "2026-09", "Inconnue"],
      series: [
        { label: "Nouveaux", values: [0, 1, 1] },
        { label: "Renouvellements", values: [1, 1, 0] },
      ],
    });
  });

  it("sums up the season: members, new and autonomous members in percent, average of the known ages, cancelled purchases, waiting lists apart", () => {
    const records = [
      purchase(1, { sex: "F", age: 10, returning: false }),
      purchase(1, { sex: "F", age: 10, returning: false, group: "Compétition" }),
      purchase(2, { sex: "H", age: 41, group: "Autonome adultes" }),
      purchase(3, { sex: "H", age: null }),
      purchase(4, { sex: "H", status: "Annulé" }),
      purchase(2, { sex: "H", status: "Annulé", group: "Compétition" }),
      purchase(5, { sex: "H", status: "Refusé" }),
      purchase(6, { status: "Annulé", season: "2025-2026" }),
      purchase(7, { group: "Liste d'attente" }),
      purchase(7, { group: "Liste d'attente collège" }),
      purchase(3, { group: "Attente compétition" }),
      purchase(8, { group: "Liste d'attente", status: "Annulé" }),
    ];

    expect(memberCards(seasonMembers(records, SEASON), records, SEASON)).toEqual({
      members: 3,
      newPercent: 33,
      autonomousPercent: 33,
      averageAge: 25.5,
      cancelled: 3,
      waiting: 2,
    });
  });

  it("counts the members of every season by sex, oldest season first", () => {
    const records = [
      purchase(1, { sex: "F", season: "2026-2027" }),
      purchase(1, { sex: "F", season: "2025-2026" }),
      purchase(2, { sex: "H", season: "2025-2026" }),
      purchase(2, { sex: "H", season: "2025-2026", group: "Compétition" }),
      purchase(3, { sex: "H", season: "2026-2027", status: "Annulé" }),
    ];

    expect(membersPerSeason(records)).toEqual({
      labels: ["2025-2026", "2026-2027"],
      series: [
        { label: "Femmes", values: [1, 1] },
        { label: "Hommes", values: [1, 0] },
      ],
    });
  });
});
