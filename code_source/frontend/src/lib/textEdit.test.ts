import { describe, expect, it } from "vitest";
import { insertText, linkTags, linkTarget, wrapSelection } from "./textEdit";

describe("body edits", () => {
  it("insert a variable in place of the selection", () => {
    expect(insertText("Bonjour X !", 8, 9, "{first_name}")).toEqual({ value: "Bonjour {first_name} !", start: 20, end: 20 });
  });

  it("wrap the selection, or a placeholder", () => {
    expect(wrapSelection("un mot ici", 3, 6, "<b>", "</b>")).toEqual({ value: "un <b>mot</b> ici", start: 6, end: 9 });
    expect(wrapSelection("", 0, 0, "<i>", "</i>")).toEqual({ value: "<i>texte</i>", start: 3, end: 8 });
  });

  it("make links from the prompt's answer", () => {
    expect(linkTarget(null)).toBeNull();
    expect(linkTarget("https://")).toBeNull();
    expect(linkTarget(" https://www.alj-escalade.fr ")).toBe("https://www.alj-escalade.fr");
    expect(linkTags('https://x.fr/?a=1&b="2"')).toEqual(['<a href="https://x.fr/?a=1&amp;b=&quot;2&quot;">', "</a>"]);
  });
});
