import { describe, expect, it } from "vitest";
import {
  addDays,
  agendaDays,
  calendarColor,
  competitionDays,
  initialMonth,
  layoutWeek,
  LEGEND,
  monthAgenda,
  monthTitle,
  monthWeeks,
  shiftMonth,
  WEEKDAYS,
} from "./calendar";
import type { Competition } from "../competitions";

const comp = (id: number, start: string, end?: string, extra: Partial<Competition> = {}): Competition => ({
  id,
  nom: `C${id}`,
  date_competition: start,
  date_fin: end,
  statut: "en_preparation",
  participants: [],
  ...extra,
});

describe("addDays", () => {
  it("rolls over months, years and leap days", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2028-03-01", -1)).toBe("2028-02-29");
    expect(addDays("2026-03-29", 1)).toBe("2026-03-30"); // daylight saving change
  });
});

describe("monthWeeks", () => {
  it("starts on the Monday before the 1st and ends on the Sunday after the last day", () => {
    const weeks = monthWeeks({ year: 2026, month: 9 }, "2026-10-27"); // October 2026: Thursday 1st
    expect(weeks).toHaveLength(5);
    expect(weeks[0]![0]).toEqual({ dateIso: "2026-09-28", dayNumber: 28, inMonth: false, isToday: false });
    expect(weeks[0]![3]!.dateIso).toBe("2026-10-01");
    expect(weeks[4]![6]).toEqual({ dateIso: "2026-11-01", dayNumber: 1, inMonth: false, isToday: false });
    expect(
      weeks
        .flat()
        .filter((d) => d.isToday)
        .map((d) => d.dateIso),
    ).toEqual(["2026-10-27"]);
  });

  it.each([
    ["a month starting on a Monday", { year: 2026, month: 5 }, 5, "2026-06-01"], // June 2026
    ["a month starting on a Sunday", { year: 2026, month: 1 }, 5, "2026-01-26"], // February 2026: Sunday 1st
    ["a February over four weeks", { year: 2027, month: 1 }, 4, "2027-02-01"], // February 2027: Monday 1st, 28 days
    ["February of a leap year", { year: 2028, month: 1 }, 5, "2028-01-31"], // Tuesday 1st, 29 days
    ["a month over six weeks", { year: 2026, month: 2 }, 6, "2026-02-23"], // March 2026: Sunday 1st, 31 days
  ])("%s", (_, month, weekCount, firstDay) => {
    const weeks = monthWeeks(month, "2000-01-01");
    expect(weeks).toHaveLength(weekCount);
    expect(weeks[0]![0]!.dateIso).toBe(firstDay);
    expect(weeks.every((w) => w.length === 7)).toBe(true);
  });

  it("counts the month's days once", () => {
    expect(
      monthWeeks({ year: 2028, month: 1 }, "2000-01-01")
        .flat()
        .filter((d) => d.inMonth),
    ).toHaveLength(29);
  });
});

describe("shiftMonth / initialMonth", () => {
  it("crosses years", () => {
    expect(shiftMonth({ year: 2026, month: 11 }, 1)).toEqual({ year: 2027, month: 0 });
    expect(shiftMonth({ year: 2026, month: 0 }, -1)).toEqual({ year: 2025, month: 11 });
  });

  it("opens on the selected competition's month, otherwise today's", () => {
    expect(initialMonth(comp(1, "2027-03-15"), "2026-10-27")).toEqual({ year: 2027, month: 2 });
    expect(initialMonth(undefined, "2026-10-27")).toEqual({ year: 2026, month: 9 });
    expect(initialMonth(comp(1, ""), "2026-10-27")).toEqual({ year: 2026, month: 9 });
  });
});

describe("competitionDays", () => {
  it("reads one day when the end is missing or before the start, nothing without a start", () => {
    expect(competitionDays(comp(1, "2026-11-14", "2026-11-15"))).toEqual(["2026-11-14", "2026-11-15"]);
    expect(competitionDays(comp(1, "2026-11-14"))).toEqual(["2026-11-14", "2026-11-14"]);
    expect(competitionDays(comp(1, "2026-11-14", "2026-11-10"))).toEqual(["2026-11-14", "2026-11-14"]);
    expect(competitionDays(comp(1, "2026-11-14T09:00:00", "2026-11-15T18:00:00"))).toEqual(["2026-11-14", "2026-11-15"]);
    expect(competitionDays(comp(1, ""))).toBeNull();
  });
});

describe("layoutWeek", () => {
  const monday = "2026-11-09";

  it("draws a weekend as one bar", () => {
    const { bars, lanes } = layoutWeek([comp(1, "2026-11-14", "2026-11-15")], monday);
    expect(lanes).toBe(1);
    expect(bars).toEqual([expect.objectContaining({ startCol: 5, span: 2, lane: 0, continuesBefore: false, continuesAfter: false })]);
  });

  it("cuts a competition crossing a week boundary on both rows", () => {
    const sundayToTuesday = comp(1, "2026-11-15", "2026-11-17");
    expect(layoutWeek([sundayToTuesday], monday).bars[0]).toMatchObject({
      startCol: 6,
      span: 1,
      continuesBefore: false,
      continuesAfter: true,
    });
    expect(layoutWeek([sundayToTuesday], "2026-11-16").bars[0]).toMatchObject({
      startCol: 0,
      span: 2,
      continuesBefore: true,
      continuesAfter: false,
    });
  });

  it("keeps a competition crossing a month boundary in the shared week", () => {
    const { bars } = layoutWeek([comp(1, "2026-10-31", "2026-11-01")], "2026-10-26");
    expect(bars[0]).toMatchObject({ startCol: 5, span: 2 });
  });

  it("stacks overlapping competitions on separate lanes, and reuses a lane once free", () => {
    const { bars, lanes } = layoutWeek(
      [comp(1, "2026-11-14", "2026-11-15"), comp(2, "2026-11-14"), comp(3, "2026-11-15"), comp(4, "2026-11-10")],
      monday,
    );
    const laneOf = Object.fromEntries(bars.map((b) => [b.competition.id, b.lane]));
    expect(laneOf).toEqual({ 4: 0, 1: 0, 2: 1, 3: 1 });
    expect(lanes).toBe(2);
  });

  it("puts three competitions on the same day on three lanes, longest first", () => {
    const { bars, lanes } = layoutWeek([comp(1, "2026-11-14"), comp(2, "2026-11-14"), comp(3, "2026-11-13", "2026-11-15")], monday);
    expect(lanes).toBe(3);
    expect(bars.map((b) => [b.competition.id, b.lane])).toEqual([
      [3, 0],
      [1, 1],
      [2, 2],
    ]);
  });

  it("leaves out the competitions of other weeks and the undated ones", () => {
    expect(layoutWeek([comp(1, "2026-11-08"), comp(2, "2026-11-16"), comp(3, "")], monday)).toEqual({ bars: [], lanes: 0 });
  });
});

describe("monthAgenda", () => {
  it("lists the competitions with a day in the month, by start then name", () => {
    const list = [
      comp(1, "2026-11-20", undefined, { nom: "Zeta" }),
      comp(2, "2026-10-31", "2026-11-01", { nom: "Over the month" }),
      comp(3, "2026-11-20", undefined, { nom: "Alpha" }),
      comp(4, "2026-12-01"),
      comp(5, ""),
    ];
    expect(monthAgenda(list, { year: 2026, month: 10 }).map((c) => c.nom)).toEqual(["Over the month", "Alpha", "Zeta"]);
  });
});

describe("labels and colours", () => {
  it("writes months, weekdays and days in French", () => {
    expect(monthTitle({ year: 2026, month: 10 })).toBe("Novembre 2026");
    expect(WEEKDAYS[0]).toBe("lun.");
    expect(WEEKDAYS[6]).toBe("dim.");
    expect(agendaDays(comp(1, "2026-11-14", "2026-11-15"))).toBe("sam. 14 nov. – dim. 15 nov.");
    expect(agendaDays(comp(1, "2026-11-14"))).toBe("sam. 14 nov.");
  });

  it("colours by discipline, slate without one or once archived", () => {
    expect(calendarColor(comp(1, "2026-11-14", undefined, { type: "Bloc" }))).toBe("violet");
    expect(calendarColor(comp(1, "2026-11-14", undefined, { type: "Escalade" }))).toBe("slate");
    expect(calendarColor(comp(1, "2026-11-14", undefined, { type: "Bloc", statut: "close" }))).toBe("slate");
    expect(LEGEND.map((l) => l.label)).toEqual(["Bloc", "Difficulté", "Vitesse", "Combiné", "Autre / non précisé"]);
  });
});
