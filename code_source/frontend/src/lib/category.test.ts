import { describe, expect, it } from "vitest";
import { categoryLabel, categoryAndSexLabel } from "./category";

describe("category", () => {
  it("labels the FFME categories, nothing for none", () => {
    expect(categoryLabel("U13")).toBe("U13");
    expect(categoryLabel("SENIOR")).toBe("Sénior");
    expect(categoryLabel("VETERAN_2")).toBe("Vétéran 2");
    expect(categoryLabel("")).toBe("");
    expect(categoryLabel(undefined)).toBe("");
  });

  it("adds the sex initial when known", () => {
    expect(categoryAndSexLabel("U13", "F")).toBe("U13 F");
    expect(categoryAndSexLabel("VETERAN_1", "H")).toBe("Vétéran 1 H");
    expect(categoryAndSexLabel("U15", null)).toBe("U15");
    expect(categoryAndSexLabel("", "F")).toBe("");
  });
});
