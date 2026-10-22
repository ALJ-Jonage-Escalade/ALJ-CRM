import { describe, expect, it } from "vitest";
import { member } from "../adherents/members.fixture";
import { detailRows, emergencyMatches, emergencyRows, seasonCounts, toDirectory } from "./directory";

const LEA = member({
  user_id: 1, purchase_id: 11, last_name: "DUPONT", first_name: "Léa", birth_date: "2014-03-02", phone: "06 12 34 56 78",
  address: "1 rue A", zip_code: "69330", city: "Jonage", emergency1_name: "Paul Dupont", emergency1_phone: "06 00 00 00 01",
  health_commitment: "Oui", document_sante: "Certificat", amount: 180, order_ref: "R-1", payer: "Paul Dupont", payer_email: "paul@example.org",
  commentaires_correctif: "à vérifier",
});

describe("toDirectory", () => {
  it("keeps contacts and emergency contacts, no health nor payment data", () => {
    const d = toDirectory({ season: "2026-2027", creneaux: [], members: [LEA] });
    const kept = d.members[0]!;
    expect(kept).toMatchObject({ last_name: "DUPONT", phone: "06 12 34 56 78", emergency1_phone: "06 00 00 00 01", payer_email: "paul@example.org" });
    for (const field of ["health_commitment", "document_sante", "amount", "order_ref", "order_date", "commentaires_correctif", "email_sent_date"]) {
      expect(kept).not.toHaveProperty(field);
    }
    expect(d.season).toBe("2026-2027");
  });
});

describe("member card", () => {
  it("lists the filled lines, and the payer when it is someone else", () => {
    const rows = detailRows(toDirectory({ season: "", creneaux: [], members: [LEA] }).members[0]!);
    expect(rows.map((r) => r.label)).toEqual(["🎂 Naissance", "📍 Adresse", "📞 Téléphone", "🚨 Urgence 1", "💳 Payeur"]);
    expect(rows[0]!.value).toBe("02/03/2014");
    expect(rows[1]!.value).toBe("1 rue A, 69330 Jonage");
    expect(rows[4]!.value).toBe("Paul Dupont (paul@example.org)");
    expect(detailRows(member({ first_name: "Léa", last_name: "Dupont", payer: "LEA DUPONT" }))).toEqual([]);
  });

  it("gives the phones to call", () => {
    expect(emergencyRows(LEA)).toEqual([
      { label: "👤 Adhérent", name: "", phone: "06 12 34 56 78" },
      { label: "🚨 Urgence 1", name: "Paul Dupont", phone: "06 00 00 00 01" },
    ]);
  });
});

describe("emergency search", () => {
  const members = [LEA, member({ last_name: "MARTIN", first_name: "Max" })];
  it.each([
    ["", null],
    ["d", null],
    ["du", ["DUPONT"]],
    ["lea dup", ["DUPONT"]],
    ["dupont léa", ["DUPONT"]],
    ["mart", ["MARTIN"]],
    ["zz", []],
  ])("%j", (search, expected) => {
    expect(emergencyMatches(members, search)?.map((m) => m.last_name) ?? null).toEqual(expected);
  });
});

describe("seasonCounts", () => {
  it("counts the cancelled memberships apart", () => {
    expect(seasonCounts([{ status_norm: "Validé" }, { status_norm: "Annulé" }, { status_norm: "En cours" }])).toEqual({ registered: 2, cancelled: 1 });
  });
});
