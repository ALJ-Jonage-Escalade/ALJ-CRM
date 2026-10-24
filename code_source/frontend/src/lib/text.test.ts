import { describe, expect, it } from "vitest";
import { plural } from "./text";

describe("plural", () => {
  it.each([
    [0, ""],
    [1, ""],
    [2, "s"],
  ])("%i: %j", (n, ending) => {
    expect(plural(n)).toBe(ending);
  });

  it("takes other endings", () => {
    expect(plural(1, "ont", "a")).toBe("a");
    expect(plural(3, "ont", "a")).toBe("ont");
  });
});
