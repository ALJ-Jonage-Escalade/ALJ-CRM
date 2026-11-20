import { describe, expect, it } from "vitest";
import { passportMarks } from "./passports";

describe("passportMarks", () => {
  it("shows each passport colour as its circle, in the file's order", () => {
    expect(passportMarks("Passeport Blanc, Passeport JAUNE, passeport orange")).toBe("⚪🟡🟠");
    expect(passportMarks("Vert; Bleu; Violet; Rouge; Noir")).toBe("🟢🔵🟣🔴⚫");
  });

  it("keeps a text without any known colour", () => {
    expect(passportMarks("Passeport Ouvert")).toBe("Passeport Ouvert");
    expect(passportMarks("")).toBe("");
  });
});
