import { describe, expect, it } from "vitest";
import { attachmentName } from "./download";

describe("attachmentName", () => {
  it.each([
    ['attachment; filename="Planning_Grille_2026-2027.xlsx"', "Planning_Grille_2026-2027.xlsx"],
    ["attachment; filename=Liste.xlsx", "Liste.xlsx"],
    ["attachment", "Planning.xlsx"],
    [null, "Planning.xlsx"],
  ])("%s", (header, name) => {
    expect(attachmentName(header, "Planning.xlsx")).toBe(name);
  });
});
