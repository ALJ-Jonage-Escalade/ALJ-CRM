import { describe, expect, it } from "vitest";
import { csvBlob, csvSafe, toCsv } from "./csv";

describe("csvSafe", () => {
  it.each([
    ['=HYPERLINK("http://x")', '\'=HYPERLINK("http://x")'],
    ["+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"],
    ["-2+3+cmd|' /C calc'!A0", "'-2+3+cmd|' /C calc'!A0"],
    ["@SUM(A1:A2)", "'@SUM(A1:A2)"],
    ["\t=1+1", "'\t=1+1"],
    ["\r=1+1", "'\r=1+1"],
    ["-", "-"],
    ["+", "+"],
  ])("neutralises a formula: %j", (value, safe) => {
    expect(csvSafe(value)).toBe(safe);
  });

  it.each(["+33 6 12 34 56 78", "+33 (0)6 12.34.56.78", "-12,5", "-3", "+1.5", "Martin", "", "a=b", "06 12 34 56 78"])(
    "keeps %j",
    (value) => {
      expect(csvSafe(value)).toBe(value);
    },
  );
});

describe("toCsv", () => {
  it("quotes every cell, doubles the quotes, separates with ; and CRLF, starts with a BOM", () => {
    expect(
      toCsv([
        ["Nom", "Prénom"],
        ['Le "Roc"', "Léo"],
      ]),
    ).toBe('\uFEFF"Nom";"Prénom"\r\n"Le ""Roc""";"Léo"');
  });

  it("writes numbers, booleans and empty cells", () => {
    expect(toCsv([[12, -3, true, null, undefined]])).toBe('\uFEFF"12";"-3";"true";"";""');
  });

  it("neutralises the formulas of the cells", () => {
    expect(toCsv([["=1+1", "+33 6 12 34 56 78"]])).toBe('\uFEFF"\'=1+1";"+33 6 12 34 56 78"');
  });

  it("gives a CSV file", async () => {
    const blob = csvBlob([["a"]]);
    expect(blob.type).toBe("text/csv;charset=utf-8");
    expect([...new Uint8Array(await blob.arrayBuffer())]).toEqual([0xef, 0xbb, 0xbf, 0x22, 0x61, 0x22]); // BOM, then "a"
  });
});
