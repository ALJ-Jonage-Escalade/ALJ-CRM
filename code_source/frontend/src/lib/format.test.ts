import { describe, expect, it } from "vitest";
import { formatDate, formatDateTime, formatDateTimeSeconds, formatDayText, formatEuros, formatTime, parseDate } from "./format";

const AT = new Date(2026, 9, 24, 14, 5, 9);

describe("dates and times", () => {
  it("writes them the French way", () => {
    expect(formatDate(AT)).toBe("24/10/2026");
    expect(formatDateTime(AT)).toBe("24/10/2026 14:05");
    expect(formatDateTimeSeconds(AT)).toBe("24/10/2026 14:05:09");
    expect(formatTime(AT)).toBe("14:05:09");
  });

  it("reads a date from a server string, null when there is none", () => {
    expect(parseDate("2026-10-24T14:05:09")).toEqual(AT);
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

describe("formatEuros", () => {
  it("writes amounts in euros, missing ones as zero", () => {
    expect(formatEuros(12.5)).toBe("12,50 €");
    expect(formatEuros(null)).toBe("0,00 €");
  });
});
