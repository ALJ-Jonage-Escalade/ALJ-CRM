import { describe, expect, it } from "vitest";
import { formatDayText, parseDate } from "./format";

describe("dates", () => {
  it("reads a date from a server string, null when there is none", () => {
    expect(parseDate("2026-10-24T14:05:09")).toEqual(new Date(2026, 9, 24, 14, 5, 9));
    expect(parseDate("")).toBeNull();
    expect(parseDate(null)).toBeNull();
    expect(parseDate("bientôt")).toBeNull();
  });

  it("writes a day held as text without going through the time zone", () => {
    expect(formatDayText("2026-09-03")).toBe("03/09/2026");
    expect(formatDayText("2026-09-03T10:00:00")).toBe("03/09/2026");
    expect(formatDayText("3/9/2026")).toBe("03/09/2026");
    expect(formatDayText("bientôt")).toBe("bientôt");
    expect(formatDayText("")).toBe("");
  });
});
