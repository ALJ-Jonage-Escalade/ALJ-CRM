import { describe, expect, it } from "vitest";
import { balanceCsv, balanceLabel, balances, searchBalances, seasons, totals } from "./balance";
import type { Competition } from "../competitions";

const TODAY = "2026-11-15";
const LIST: Competition[] = [
  {
    id: 1,
    nom: "Open",
    date_competition: "2026-10-04",
    prix: 15,
    participants: [
      { adherent_id: 1, nom: "Martin", prenom: "Léo", selectionne: true, statut_paiement: "paye", montant_paye: 15 },
      { adherent_id: 2, nom: "Durand", prenom: "Zoé", selectionne: true, statut_paiement: "en_attente" },
      { adherent_id: 3, nom: "Abel", prenom: "Max", selectionne: false, statut_paiement: "non_invite" },
    ],
  },
  {
    id: 2,
    nom: "Coupe",
    date_competition: "2026-12-01",
    prix: 10,
    participants: [
      { adherent_id: 1, nom: "Martin", prenom: "Léo", selectionne: false, statut_paiement: "annule_reporte", montant_paye: 10 },
      { adherent_id: 2, nom: "Durand", prenom: "Zoé", selectionne: false, statut_paiement: "annule_perdu", montant_paye: 10 },
    ],
  },
  {
    id: 3,
    nom: "Ancienne",
    date_competition: "2026-03-01",
    prix: 8,
    participants: [{ adherent_id: 1, nom: "Martin", prenom: "Léo", selectionne: true }],
  },
  { id: 4, nom: "Sans date", prix: 5, participants: [{ adherent_id: 3, nom: "Abel", prenom: "Max", selectionne: true }] },
];

describe("balance", () => {
  it("lists the seasons with competitions and the current one", () => {
    expect(seasons(LIST, TODAY)).toEqual(["2026-2027", "2025-2026"]);
  });

  it("adds up what is due and paid, a carried-over payment as a credit, a lost one balanced", () => {
    const list = balances(LIST, "2026-2027", TODAY);
    expect(list.map((b) => [b.nom, b.due, b.paid, b.remaining])).toEqual([
      ["ABEL", 5, 0, 5], // undated: current season
      ["DURAND", 25, 10, 15], // 15 due + 10 lost (paid)
      ["MARTIN", 15, 25, -10], // 10 carried over
    ]);
    expect(list.find((b) => b.nom === "MARTIN")!.lines.map((l) => [l.competition.nom, l.due, l.carriedOver])).toEqual([
      ["Open", 15, false],
      ["Coupe", 0, true],
    ]);
    expect(totals(list)).toEqual({ due: 45, paid: 35, remaining: 10 });
    expect(balances(LIST, "2025-2026", TODAY).map((b) => [b.nom, b.remaining])).toEqual([["MARTIN", 8]]);
  });

  it("flags a paid competition missed, and labels the balance", () => {
    const list = balances(LIST, "2026-2027", TODAY);
    expect(list.find((b) => b.nom === "MARTIN")!.absent).toBe(true); // Open is over, not checked in
    const checkedIn = LIST.map((c) => (c.id === 1 ? { ...c, participants: c.participants!.map((p) => ({ ...p, present: true })) } : c));
    expect(balances(checkedIn, "2026-2027", TODAY).find((b) => b.nom === "MARTIN")!.absent).toBe(false);
    expect(balanceLabel({ remaining: 15 }).tone).toBe("due");
    expect(balanceLabel({ remaining: -10 }).tone).toBe("credit");
    expect(balanceLabel({ remaining: 0 }).text).toBe("✅ Équilibré");
  });

  it("keeps the contact details and tariff of the most recent entry that has them", () => {
    const entries: Competition[] = [
      {
        id: 1,
        nom: "Open",
        date_competition: "2026-10-04",
        participants: [{ adherent_id: 1, nom: "Martin", prenom: "Léo", selectionne: true, email: "old@x.fr", phone: "06", tarif: "U12" }],
      },
      {
        id: 2,
        nom: "Coupe",
        date_competition: "2026-12-01",
        participants: [{ adherent_id: 1, nom: "Martin", prenom: "Léo", selectionne: true, email: "new@x.fr", phone: "", tarif: "U14" }],
      },
    ];
    const [martin] = balances(entries, "2026-2027", TODAY);
    expect([martin!.email, martin!.phone, martin!.group]).toEqual(["new@x.fr", "06", "U14"]);
  });

  it("searches and exports", () => {
    const list = balances(LIST, "2026-2027", TODAY);
    expect(searchBalances(list, "leo martin").map((b) => b.nom)).toEqual(["MARTIN"]);
    const csv = balanceCsv(list);
    expect(csv[0]![0]).toBe("Nom");
    expect(csv[3]).toEqual(["MARTIN", "Léo", "", 2, "15.00", "25.00", "-10.00", "Coupe : reporté | Absent à une épreuve payée"]);
  });
});
