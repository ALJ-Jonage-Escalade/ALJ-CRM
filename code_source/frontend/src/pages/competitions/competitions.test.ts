import { describe, expect, it } from "vitest";
import { counts, filterRows, groupRows, participantRows, payment, period, sortCompetitions, toMemberSlots, UNIDENTIFIED, type Competition } from "./competitions";

const comp = (change: Partial<Competition>): Competition => ({ id: 1, nom: "C", participants: [], ...change });

describe("competitions", () => {
  it("sorts the most recent first, undated last", () => {
    const list = [comp({ id: 1, date_competition: "2026-03-01" }), comp({ id: 2 }), comp({ id: 3, date_competition: "2026-05-01" })];
    expect(sortCompetitions(list).map((c) => c.id)).toEqual([3, 1, 2]);
  });

  it.each([
    [{}, "sans date"],
    [{ date_competition: "2026-03-15" }, "15/03/2026"],
    [{ date_competition: "2026-03-15", date_fin: "2026-03-16" }, "15/03/2026 → 16/03/2026"],
    [{ date_competition: "2026-03-15", date_fin: "2026-03-15" }, "15/03/2026"],
  ])("period %j", (change, expected) => {
    expect(period(comp(change))).toBe(expected);
  });

  it("labels the payment statuses", () => {
    expect(payment("paye").label).toBe("Payé");
    expect(payment("annule_reporte").label).toBe("Annulé — report");
    expect(payment("inconnu").label).toBe("inconnu");
  });

  it("keeps only the grouping fields of the member directory", () => {
    expect(toMemberSlots([{ id: 1, nom: "X", tarif: "T", creneau_groupe: "G", phone: "06" }])).toEqual([{ id: 1, tarif: "T", creneau_groupe: "G" }]);
  });
});

describe("participants", () => {
  const c = comp({
    participants: [
      { adherent_id: 1, nom: "MARTIN", prenom: "Léo", selectionne: true, statut_paiement: "paye", tarif: "Ancien", urgence_nom: "Copie", urgence_tel: "0600" },
      { adherent_id: 2, nom: "DURAND", prenom: "Zoé", selectionne: true, statut_paiement: "en_attente", urgence_tel: "0611" },
      { adherent_id: 3, nom: "ABEL", prenom: "Max", selectionne: false, statut_paiement: "non_invite" },
    ],
  });
  const members = [{ id: 1, tarif: "Compétition U18", creneau_groupe: "Compét. U18" }];
  const contacts = [{
    adherent_id: 2, last_name: "DURAND", first_name: "Zoé", phone: "06 22", creneau_groupe: "Compét. U14",
    emergency1_name: "Paul", emergency1_phone: "06 01", emergency2_name: "", emergency2_phone: "",
  }];

  it("takes the current tariff and slot group, phone and emergency contacts when known", () => {
    const rows = participantRows(c, members, contacts);
    expect(rows.map((r) => [r.group, r.tarif])).toEqual([["Compét. U18", "Compétition U18"], ["Compét. U14", ""], [UNIDENTIFIED, ""]]);
    expect(rows[0]!.emergency).toEqual([{ name: "Copie", phone: "0600" }]);  // copied when added
    expect(rows[1]!.emergency).toEqual([{ name: "Paul", phone: "06 01" }]);  // the competitor's contacts
    expect(rows[1]!.phone).toBe("06 22");
  });

  it("counts, filters and groups (« Non identifiés » last)", () => {
    const rows = participantRows(c, members, contacts);
    expect(counts(rows)).toEqual({ all: 3, selected: 2, unpaid: 1, paid: 1 });
    expect(filterRows(rows, "unpaid").map((r) => r.nom)).toEqual(["DURAND"]);
    expect(filterRows(rows, "selected")).toHaveLength(2);
    expect(groupRows(rows).map(([g]) => g)).toEqual(["Compét. U14", "Compét. U18", UNIDENTIFIED]);
  });
});
