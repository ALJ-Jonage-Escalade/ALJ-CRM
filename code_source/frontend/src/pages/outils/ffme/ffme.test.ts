import { describe, expect, it } from "vitest";
import {
  blockedUserIds,
  changeMatches,
  licenseeMatches,
  manualMatches,
  readBase64,
  sortChanges,
  sortedMembers,
  type Licensee,
  type Member,
  type RowChange,
} from "./ffme";

const ROW = (row_number: number, nom: string): Licensee => ({
  row_number,
  nom,
  prenom: "Tom",
  licence: "998877",
  birth_date: "22/07/2009",
  passeports: "Bleu",
  diplomes: "",
  document_sante: "Certificat",
});
const CHANGE = (row_number: number, last_name: string, more: Partial<RowChange> = {}): RowChange => ({
  row_number,
  user_id: row_number,
  last_name,
  first_name: "Tom",
  birth_date: "",
  licence: "636947",
  source: "licence",
  licence_conflict: "",
  changes: [{ field: "statut", old: "Validé", new: "Terminé" }],
  no_active_registration: false,
  duplicate: false,
  ...more,
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
    const rows = [ROW(3, "DUPONT"), ROW(4, "DURAND"), ROW(5, "MOREL")];
    expect(manualMatches(rows, [null, 12, 0])).toEqual([
      { row_number: 4, user_id: 12 },
      { row_number: 5, user_id: 0 },
    ]);
    expect(manualMatches(rows, [])).toEqual([]);
  });

  it("sorts the changes by what needs a look: matched twice, licence held by another member or no active registration, manual, by name, by licence", () => {
    const rows = [
      CHANGE(1, "Zola"),
      CHANGE(2, "Petit", { source: "nom" }),
      CHANGE(3, "Morel", { source: "manuel" }),
      CHANGE(4, "Durand", { no_active_registration: true }),
      CHANGE(5, "Dupont", { duplicate: true }),
      CHANGE(6, "Évans"),
      CHANGE(7, "Dupuis", { licence_conflict: "MARTIN Léo" }),
    ];
    expect(sortChanges(rows).map((row) => row.row_number)).toEqual([5, 7, 4, 3, 2, 6, 1]);
  });

  it("searches by name or licence, accents and case ignored", () => {
    const row = CHANGE(3, "Hélène");
    expect(["helene", " TOM ", "6369", ""].map((query) => changeMatches(row, query))).toEqual([true, true, true, true]);
    expect(changeMatches(row, "998877")).toBe(false);
    expect(["dupont", "9988"].map((query) => licenseeMatches(ROW(3, "DUPONT"), query))).toEqual([true, true]);
    expect(licenseeMatches(ROW(3, "DUPONT"), "636947")).toBe(false);
  });

  it("blocks a member while several ticked rows point to them", () => {
    const rows = [CHANGE(3, "Dupont", { user_id: 7 }), CHANGE(4, "Dupont", { user_id: 7, source: "manuel" }), CHANGE(5, "Morel")];
    expect([...blockedUserIds(rows, new Set())]).toEqual([7]);
    expect([...blockedUserIds(rows, new Set([4]))]).toEqual([]);
  });
});
