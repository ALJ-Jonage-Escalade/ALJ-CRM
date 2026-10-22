import { describe, expect, it } from "vitest";
import { isStaff, roleLabel } from "./roles";

describe("roles", () => {
  it.each([
    ["admin", "🛡️ Administrateur", true],
    ["coach", "🏃 Coach", true],
    ["readonly", "👁️ Lecture seule", false],
    [null, "⛔ Non autorisé", false],
  ] as const)("%s → %s, staff: %s", (role, label, staff) => {
    expect(roleLabel(role)).toBe(label);
    expect(isStaff(role)).toBe(staff);
  });
});
