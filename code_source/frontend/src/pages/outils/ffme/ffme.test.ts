import { describe, expect, it } from "vitest";
import { manualMatches, readBase64, sortedMembers, type Licensee, type Member } from "./ffme";

const ROW = (nom: string): Licensee => ({
  nom,
  prenom: "Tom",
  licence: "998877",
  birth_date: "22/07/2009",
  passeports: "Bleu",
  diplomes: "",
  document_sante: "Certificat",
});
const MEMBER = (id: number, last_name: string, first_name: string): Member => ({ id, last_name, first_name, birth_date: "" });

describe("ffme import", () => {
  it("reads a file in base64, by chunks", async () => {
    expect(await readBase64(new Blob(["Léo"]))).toBe(btoa(String.fromCharCode(0x4c, 0xc3, 0xa9, 0x6f)));
    const big = new Uint8Array(100_000).map((_, i) => i % 256);
    const decoded = Uint8Array.from(atob(await readBase64(new Blob([big]))), (c) => c.charCodeAt(0));
    expect(decoded).toEqual(big);
  });

  it("sorts the members, accents and case ignored", () => {
    const sorted = sortedMembers([MEMBER(1, "Petit", "Max"), MEMBER(2, "ÉVANS", "Lily"), MEMBER(3, "petit", "Anna")]);
    expect(sorted.map((m) => m.id)).toEqual([2, 3, 1]);
  });

  it("keeps the rows linked to a member", () => {
    const rows = [ROW("DUPONT"), ROW("DURAND"), ROW("MOREL")];
    expect(manualMatches(rows, [null, 12, 0])).toEqual([
      { user_id: 12, nom: "DURAND", prenom: "Tom", licence: "998877", passeports: "Bleu", diplomes: "", document_sante: "Certificat" },
      { user_id: 0, nom: "MOREL", prenom: "Tom", licence: "998877", passeports: "Bleu", diplomes: "", document_sante: "Certificat" },
    ]);
    expect(manualMatches(rows, [])).toEqual([]);
  });
});
