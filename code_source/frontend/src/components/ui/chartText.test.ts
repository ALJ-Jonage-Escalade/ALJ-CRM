import { describe, expect, it } from "vitest";
import { hoverText, shortLabel } from "./chartText";

describe("chart texts", () => {
  it("keeps the beginning of a long axis label, cut with an ellipsis", () => {
    expect(shortLabel("Compétition jeunes 2015-2016", 12)).toBe("Compétition…");
    expect(shortLabel("Adulte", 12)).toBe("Adulte");
  });

  it("reads the hovered bar in full: its whole label and the value of each series", () => {
    expect(hoverText("Compétition jeunes 2015-2016", [{ label: "Adhérents", data: [4, 12] }], 1, "")).toBe(
      "Compétition jeunes 2015-2016 : 12",
    );
    expect(
      hoverText(
        "Adulte",
        [
          { label: "Femmes", data: [33] },
          { label: "Hommes", data: [67] },
        ],
        0,
        "%",
      ),
    ).toBe("Adulte · Femmes 33 % · Hommes 67 %");
  });
});
