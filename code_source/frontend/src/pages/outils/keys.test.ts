import { describe, expect, it } from "vitest";
import { keyCounts, shownKeys, type Key } from "./keys";

const key = (id: number, code: string, status: Key["status"] = "available"): Key => ({ id, code, status });

describe("shownKeys", () => {
  it("keeps every key without a search", () => {
    expect(shownKeys([key(1, "10"), key(2, "2")], " ")).toHaveLength(2);
  });

  it("filters on the code, whatever its case", () => {
    const keys = [key(1, "A12"), key(2, "B7")];
    expect(shownKeys(keys, " a1 ").map((k) => k.code)).toEqual(["A12"]);
  });
});

describe("keyCounts", () => {
  it("counts the keys of each status", () => {
    const keys = [key(1, "1", "assigned"), key(2, "2"), key(3, "3", "archived"), key(4, "4", "assigned")];
    expect(keyCounts(keys)).toEqual({ assigned: 2, available: 1, archived: 1 });
  });
});
