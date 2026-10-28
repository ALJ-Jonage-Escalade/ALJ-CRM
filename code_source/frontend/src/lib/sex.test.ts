import { describe, expect, it } from "vitest";
import { sexLabel, sexPluralLabel } from "./sex";

describe("sex labels", () => {
  it("labels the FFME codes", () => {
    expect(sexLabel("F")).toBe("Femme");
    expect(sexLabel("H")).toBe("Homme");
    expect(sexPluralLabel("F")).toBe("Femmes");
    expect(sexPluralLabel("H")).toBe("Hommes");
  });

  it("labels a sex not given, or missing from a list saved offline before the field existed", () => {
    expect(sexLabel(null)).toBe("Non renseigné");
    expect(sexLabel(undefined)).toBe("Non renseigné");
    expect(sexPluralLabel(null)).toBe("Non renseigné");
  });
});
