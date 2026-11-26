import { describe, expect, it } from "vitest";
import { posterBlocks, posterSummary } from "./poster";
import type { Participant } from "../competitions";

const climber = (nom: string, prenom: string, categorie_ffme: string, classement: string, total_categorie = 20): Participant => ({
  nom,
  prenom,
  categorie_ffme,
  classement,
  total_categorie,
});

const titles = (participants: Participant[]): string[] => posterBlocks(participants).map((block) => block.title);

describe("posterBlocks", () => {
  it("lists the ranked climbers of a category and leaves out the unranked", () => {
    const blocks = posterBlocks([
      climber("BASSO", "Chloé", "U13 Femme", "8", 25),
      climber("ABSENTE", "Lou", "U13 Femme", ""),
      { nom: "SANS", prenom: "Résultat" },
    ]);

    expect(blocks).toEqual([{ title: "U13 Femme", lines: [{ name: "BASSO Chloé", place: "8 / 25", color: "slate" }] }]);
  });

  it("merges the spellings of a MyCompet category into one block", () => {
    const variants = ["U13 Femme", "U13Femme", "u13 F", "[U13] Femme"].map((label, i) => climber(`NOM${i}`, "A", label, String(i + 4)));

    expect(titles(variants)).toEqual(["U13 Femme"]);
  });

  it("keeps a category without a sex as is, whatever the climber's sex", () => {
    expect(titles([{ ...climber("COCHE", "Éden", "U17", "6"), sex: "H" }])).toEqual(["U17"]);
  });

  it("orders the blocks by age, women first, unknown categories last", () => {
    const labels = ["Open", "Vétéran H", "U17 Homme", "U9", "Sénior F", "U13 Homme", "U13 Femme", "U17"];

    expect(titles(labels.map((label) => climber("X", "Y", label, "1")))).toEqual([
      "U9",
      "U13 Femme",
      "U13 Homme",
      "U17",
      "U17 Homme",
      "Sénior Femme",
      "Vétéran Homme",
      "Open",
    ]);
  });

  it("orders the climbers of a block by place, then by name", () => {
    const [block] = posterBlocks([
      climber("LOMBARD", "Matisse", "U13 H", "11"),
      climber("VELEINE", "Gonzague", "U13 H", "4"),
      climber("ABRIAL", "Arthur", "U13 H", "4"),
    ]);

    expect(block?.lines.map((line) => line.name)).toEqual(["ABRIAL Arthur", "VELEINE Gonzague", "LOMBARD Matisse"]);
  });

  it("marks the podium places with their medal and colour, as on the competition page", () => {
    const [block] = posterBlocks(["1", "2", "3", "4"].map((place) => climber(`C${place}`, "A", "U15 F", place, 20)));

    expect(block?.lines.map(({ place, color }) => [place, color])).toEqual([
      ["🥇 1 / 20", "gold"],
      ["🥈 2 / 20", "silver"],
      ["🥉 3 / 20", "bronze"],
      ["4 / 20", "slate"],
    ]);
  });

  it("names the adult categories in full", () => {
    expect(titles([climber("A", "A", "Senior H", "1"), climber("B", "B", "Vétéran Femme", "2")])).toEqual([
      "Sénior Homme",
      "Vétéran Femme",
    ]);
  });
});

describe("posterSummary", () => {
  it("counts the ranked climbers and the podium places, every category together", () => {
    const blocks = posterBlocks([
      climber("A", "A", "U13 F", "1"),
      climber("B", "B", "U13 F", "5"),
      climber("C", "C", "U15 H", "3"),
      climber("D", "D", "U15 H", ""),
    ]);

    expect(posterSummary(blocks)).toEqual({ ranked: 3, podiums: 2 });
  });
});
