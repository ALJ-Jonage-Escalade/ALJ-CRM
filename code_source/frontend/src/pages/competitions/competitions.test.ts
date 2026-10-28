import { describe, expect, it } from "vitest";
import {
  coachChoices,
  counts,
  discipline,
  disciplineColor,
  draftBody,
  draftErrors,
  draftOf,
  filterCompetitions,
  filterRows,
  groupRows,
  hasPaid,
  isNotInvited,
  memberMatches,
  participantCsv,
  participantRows,
  period,
  ranking,
  sortCompetitions,
  toMemberSlots,
  UNIDENTIFIED,
  type Competition,
  type MemberSlot,
} from "./competitions";

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

  it("badges the disciplines, not « escalade »", () => {
    expect(discipline({ id: 1, type: " Bloc " })).toBe("Bloc");
    expect(discipline({ id: 1, type: "Escalade" })).toBe("");
    expect(disciplineColor("VITESSE")).toBe("amber");
    expect(disciplineColor("Paraescalade")).toBe("blue");
  });

  it("keeps what the screen needs of the member directory, not the phones", () => {
    expect(
      toMemberSlots([{ id: 1, nom: "X", prenom: "Y", num_licence: "123", email: "x@y.fr", tarif: "T", creneau_groupe: "G", phone: "06" }]),
    ).toEqual([
      {
        id: 1,
        nom: "X",
        prenom: "Y",
        licence_ffme: "123",
        email: "x@y.fr",
        email_secondaire: "",
        tarif: "T",
        creneau_groupe: "G",
      },
    ]);
  });

  it("filters by search (name, place, discipline) and date", () => {
    const list = [
      comp({ id: 1, nom: "Open de Lyon", date_competition: "2026-10-01" }),
      comp({ id: 2, nom: "Coupe", lieu: "Saint-Étienne", type: "Bloc", date_competition: "2026-12-01", date_fin: "2026-12-02" }),
      comp({ id: 3, nom: "Sans date" }),
    ];
    const ids = (s: string, w: "all" | "upcoming" | "past") => filterCompetitions(list, s, w, "2026-11-01").map((c) => c.id);
    expect(ids("etienne", "all")).toEqual([2]);
    expect(ids("bloc", "all")).toEqual([2]);
    expect(ids("", "past")).toEqual([1]);
    expect(ids("", "upcoming")).toEqual([2, 3]);
  });

  it("checks and builds the form", () => {
    expect(draftErrors(draftOf())).toEqual({ nom: "Le nom de l'épreuve est obligatoire." });
    expect(draftErrors({ ...draftOf(), nom: "A", prix: "-2", date_fin: "2026-01-01" })).toEqual({
      prix: "Montant invalide.",
      date_fin: "Indiquez d'abord la date de début.",
    });
    const draft = { ...draftOf(), nom: " Open ", date_competition: "2026-03-14", date_fin: "2026-03-13", prix: "12,5", coach_ids: [3, 1] };
    expect(draftBody(draft)).toMatchObject({
      nom: "Open",
      date_competition: "2026-03-14",
      date_fin: "2026-03-14",
      prix: 12.5,
      coach_ids: [3, 1],
    });
    expect(draftBody({ ...draft, date_fin: "2026-03-15" }).date_fin).toBe("2026-03-15");
    const edited = draftOf(comp({ nom: "X", date_competition: "2026-03-14", date_fin: "2026-03-14", prix: 9, lieu: "Lyon" }));
    expect([edited.date_fin, edited.prix, edited.lieu]).toEqual(["", "9", "Lyon"]);
  });

  it("offers the competition's coaches first, in their order, then the others by name", () => {
    const coaches = [
      { id: 1, nom: "Zoé" },
      { id: 2, nom: "Alice" },
      { id: 3, nom: "Bob" },
    ];
    expect(coachChoices(coaches, [3, 1]).map((c) => c.id)).toEqual([3, 1, 2]);
    expect(coachChoices(coaches, []).map((c) => c.nom)).toEqual(["Alice", "Bob", "Zoé"]);
  });
});

describe("participants", () => {
  const c = comp({
    participants: [
      {
        adherent_id: 1,
        nom: "MARTIN",
        prenom: "Léo",
        selectionne: true,
        statut_paiement: "paye",
        montant_paye: 12,
        tarif: "Ancien",
        urgence_nom: "Copie",
        urgence_tel: "0600",
        classement: "1",
      },
      {
        adherent_id: 2,
        nom: "DURAND",
        prenom: "Zoé",
        selectionne: true,
        statut_paiement: "en_attente",
        urgence_tel: "0611",
        email: "copie@x.fr",
      },
      { adherent_id: 3, nom: "ABEL", prenom: "Max", selectionne: false, statut_paiement: "non_invite", present: true },
    ],
  });
  const members: MemberSlot[] = [{ id: 1, tarif: "Compétition U18", creneau_groupe: "Compét. U18", email: "leo@x.fr" }];
  const contacts = [
    {
      adherent_id: 2,
      last_name: "DURAND",
      first_name: "Zoé",
      phone: "06 22",
      creneau_groupe: "Compét. U14",
      emergency1_name: "Paul",
      emergency1_phone: "06 01",
      emergency2_name: "",
      emergency2_phone: "",
    },
  ];

  it("takes the current tariff and slot group, phone, e-mail and emergency contacts when known", () => {
    const rows = participantRows(c, members, contacts);
    expect(rows.map((r) => [r.group, r.tarif])).toEqual([
      ["Compét. U18", "Compétition U18"],
      ["Compét. U14", ""],
      [UNIDENTIFIED, ""],
    ]);
    expect(rows[0]!.emergency).toEqual([{ name: "Copie", phone: "0600" }]); // copied when added
    expect(rows[1]!.emergency).toEqual([{ name: "Paul", phone: "06 01" }]); // the competitor's contacts
    expect(rows[1]!.phone).toBe("06 22");
    expect(rows.map((r) => r.email)).toEqual(["leo@x.fr", "copie@x.fr", ""]);
  });

  it("shows the changes waiting in the outbox", () => {
    const rows = participantRows(c, members, contacts, (id, flag) => (id === 1 && flag === "selectionne" ? false : undefined));
    expect([rows[0]!.selectionne, rows[0]!.queued]).toEqual([false, { selectionne: true, present: false }]);
    expect(rows[1]!.queued).toEqual({ selectionne: false, present: false });
  });

  it("counts, filters, searches and groups (« Non identifiés » last)", () => {
    const rows = participantRows(c, members, contacts);
    expect(counts(rows)).toEqual({ all: 3, selected: 2, unpaid: 1, paid: 1, present: 1 });
    expect(filterRows(rows, "unpaid").map((r) => r.nom)).toEqual(["DURAND"]);
    expect(filterRows(rows, "selected")).toHaveLength(2);
    expect(filterRows(rows, "notInvited").map((r) => r.nom)).toEqual(["ABEL"]);
    expect(filterRows(rows, "all", "zoe").map((r) => r.nom)).toEqual(["DURAND"]);
    expect(groupRows(rows).map(([g]) => g)).toEqual(["Compét. U14", "Compét. U18", UNIDENTIFIED]);
  });

  it("tells who paid, who was never invited, and their ranking", () => {
    const [leo, zoe, max] = c.participants!;
    expect([hasPaid(leo!), hasPaid(zoe!), hasPaid({ ...leo!, statut_paiement: "annule_reporte" })]).toEqual([true, false, false]);
    expect([isNotInvited(max!), isNotInvited(zoe!)]).toEqual([true, false]);
    expect(ranking(leo!)).toBe("🥇 1er");
    expect(ranking({ classement: "4", total_categorie: 23 })).toBe("🏅 4 / 23");
    expect(ranking({})).toBe("");
  });

  it("finds members to add, not listed yet", () => {
    const all: MemberSlot[] = [
      { id: 1, nom: "MARTIN", prenom: "Léo" },
      { id: 4, nom: "MARTINEZ", prenom: "Éva", licence_ffme: "123456" },
    ];
    expect(memberMatches(all, c, "m")).toEqual([]);
    expect(memberMatches(all, c, "mart").map((m) => m.id)).toEqual([4]);
    expect(memberMatches(all, c, "eva").map((m) => m.id)).toEqual([4]);
    expect(memberMatches(all, c, "1234").map((m) => m.id)).toEqual([4]);
  });

  it("exports the participants", () => {
    const rows = participantCsv(participantRows(c, members, contacts));
    expect(rows[0]!.slice(0, 3)).toEqual(["Nom", "Prénom", "N° Licence"]);
    expect(rows.slice(1).map((r) => [r[0], r[4], r[5], r[6]])).toEqual([
      ["DURAND", "", "Oui", "En attente"],
      ["MARTIN", "1er", "Oui", "Payé"],
      ["ABEL", "", "Non", "Non invité"],
    ]);
  });
});
