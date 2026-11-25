import { describe, expect, it } from "vitest";
import {
  athleteContactCards,
  coachChoices,
  competitionMembersRead,
  competitorStatusesLabel,
  counts,
  defaultDeadline,
  shownDiscipline,
  disciplineColor,
  draftBody,
  draftErrors,
  draftOf,
  filterCompetitions,
  countLine,
  filterRows,
  groupFilters,
  groupRows,
  hasPaid,
  isNotInvited,
  memberMatches,
  participantCsv,
  participantRows,
  periodText,
  podiumIcon,
  rankingColor,
  rankingText,
  seasonOf,
  seasons,
  sortCompetitions,
  toMemberSlots,
  UNIDENTIFIED,
  type Competition,
  type CompetitorContact,
  type SavedCompetitorContact,
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
    [{ date_competition: "2026-03-15", date_fin: "2026-03-16" }, "15/03 au 16/03/2026"],
    [{ date_competition: "2026-12-31", date_fin: "2027-01-01" }, "31/12/2026 au 01/01/2027"],
    [{ date_competition: "2026-03-15", date_fin: "2026-03-15" }, "15/03/2026"],
  ])("period %j", (change, expected) => {
    expect(periodText(comp(change))).toBe(expected);
  });

  it.each([
    ["2026-09-01", "2026-2027"],
    ["2027-08-31", "2026-2027"],
    ["2026-08-31T10:00:00", "2025-2026"],
    [undefined, ""],
    ["", ""],
    ["31/08/2026", ""],
  ])("seasonOf %s", (iso, expected) => {
    expect(seasonOf(iso)).toBe(expected);
  });

  it("lists the seasons with competitions and the current one, newest first; undated ones add none", () => {
    const list = [comp({ date_competition: "2026-03-01" }), comp({ date_competition: "2024-10-12" }), comp({})];
    expect(seasons(list, "2026-11-16")).toEqual(["2026-2027", "2025-2026", "2024-2025"]);
    expect(seasons([], "2026-11-16")).toEqual(["2026-2027"]);
  });

  it("badges the disciplines, not « escalade »", () => {
    expect(shownDiscipline({ id: 1, type: " Bloc " })).toBe("Bloc");
    expect(shownDiscipline({ id: 1, type: "Escalade" })).toBe("");
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
    expect(defaultDeadline("2026-03-14")).toBe("2026-03-07");
    expect(defaultDeadline("")).toBe("");
    const draft = { ...draftOf(), nom: " Open ", date_competition: "2026-03-14", date_fin: "2026-03-13", prix: "12,5", coach_ids: [3, 1] };
    expect(draftBody(draft)).toMatchObject({
      nom: "Open",
      date_competition: "2026-03-14",
      date_fin: "2026-03-14",
      deadline: "",
      prix: 12.5,
      coach_ids: [3, 1],
    });
    expect(draftBody({ ...draft, date_fin: "2026-03-15" }).date_fin).toBe("2026-03-15");
    expect(draftBody({ ...draft, deadline: "2026-03-01" }).deadline).toBe("2026-03-01");
    const edited = draftOf(comp({ nom: "X", date_competition: "2026-03-14", date_fin: "2026-03-14", prix: 9, lieu: "Lyon" }));
    expect([edited.date_fin, edited.prix, edited.lieu, edited.deadline]).toEqual(["", "9", "Lyon", "2026-03-07"]);
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
      emergency_contacts: [{ name: "Paul", phone: "06 01" }],
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

  it("filters by slot group, offering the groups where someone takes part", () => {
    const rows = participantRows(c, members, contacts);
    // « Non identifiés »: nobody takes part, no filter
    expect(groupFilters(rows)).toEqual([
      { group: "Compét. U14", n: 1 },
      { group: "Compét. U18", n: 1 },
    ]);
    expect(filterRows(rows, "all", "", "Compét. U14").map((r) => r.nom)).toEqual(["DURAND"]);
    expect(countLine(counts(rows), "all", 1, "Compét. U14")).toBe("1 compétiteur en « Compét. U14 »");
  });

  it("splits a slot group by sex, girls first, unknown sex last", () => {
    const climber = (adherent_id: number, sex: "F" | "H" | null, selectionne = true) => ({
      adherent_id,
      nom: `N${adherent_id}`,
      sex,
      selectionne,
    });
    const group = comp({ participants: [climber(1, "H"), climber(2, null), climber(3, "F"), climber(4, "H"), climber(5, "F", false)] });
    const slots: MemberSlot[] = [1, 2, 3, 4, 5].map((id) => ({ id, creneau_groupe: "U11-U13" }));
    const rows = participantRows(group, slots, []);
    expect(groupFilters(rows)).toEqual([
      { group: "U11-U13 - F", n: 2 },
      { group: "U11-U13 - H", n: 2 },
      { group: "U11-U13", n: 1 },
    ]);
    expect(filterRows(rows, "all", "", "U11-U13 - H").map((r) => r.adherent_id)).toEqual([1, 4]);
    expect(filterRows(rows, "all", "", "U11-U13").map((r) => r.adherent_id)).toEqual([2]);
  });

  it("tells who paid, who was never invited, and their ranking", () => {
    const [leo, zoe, max] = c.participants!;
    expect([hasPaid(leo!), hasPaid(zoe!), hasPaid({ ...leo!, statut_paiement: "annule_reporte" })]).toEqual([true, false, false]);
    expect([isNotInvited(max!), isNotInvited(zoe!)]).toEqual([true, false]);
    expect(rankingText(leo!)).toBe("🥇 1er");
    expect(rankingText({ classement: "4", total_categorie: 23 })).toBe("4 / 23");
    expect(rankingText({ resultat_ffme: "12e" })).toBe("12e");
    expect(rankingText({})).toBe("");
  });

  it.each([
    ["1", "🥇", "gold"],
    ["2", "🥈", "silver"],
    ["3", "🥉", "bronze"],
    ["4", "", "slate"],
    ["", "", "slate"],
  ])("gives rank %s the medal %s and the %s pill", (classement, icon, color) => {
    expect(podiumIcon({ classement })).toBe(icon);
    expect(rankingColor({ classement })).toBe(color);
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

  it("asks the server for the members at the competitor statuses only", () => {
    expect(competitionMembersRead()).toEqual({ path: "/api/competition-members", query: { status: ["Terminé"] } });
    expect(competitorStatusesLabel).toBe("« Terminé »");
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

  it("builds one card per contact, e-mail on the athlete's card only", () => {
    const p = { nom: "DUPONT", prenom: "Lucas", email: "lucas@test.fr" };
    const member: MemberSlot = { id: 10, nom: "DUPONT", prenom: "Lucas", email: "lucas@test.fr", email_secondaire: "maman@test.fr" };
    const contact: CompetitorContact = {
      adherent_id: 10,
      last_name: "DUPONT",
      first_name: "Lucas",
      phone: "06 00 11 22 33",
      creneau_groupe: "",
      emergency_contacts: [
        { name: "Dupont Marie", phone: "06 11 11 11 11" },
        { name: "Dupont Jean", phone: "06 22 22 22 22" },
        { name: "Dupont Anna", phone: "06 33 33 33 33" },
      ],
      emergency1_name: "Dupont Marie",
      emergency1_phone: "06 11 11 11 11",
      emergency2_name: "Dupont Jean",
      emergency2_phone: "06 22 22 22 22",
    };
    expect(athleteContactCards(p, member, contact)).toEqual([
      { role: "athlete", title: "🧗 Athlète", name: "Lucas DUPONT", phone: "06 00 11 22 33", email: "lucas@test.fr" },
      { role: "emergency", title: "🚨 Contact d'urgence 1", name: "Dupont Marie", phone: "06 11 11 11 11", email: "" },
      { role: "emergency", title: "🚨 Contact d'urgence 2", name: "Dupont Jean", phone: "06 22 22 22 22", email: "" },
      { role: "emergency", title: "🚨 Contact d'urgence 3", name: "Dupont Anna", phone: "06 33 33 33 33", email: "" },
    ]);
  });

  it("lists every contact of a competitor as a link, and reads a copy saved offline before the list existed", () => {
    const entry = { adherent_id: 2, last_name: "", first_name: "", phone: "", creneau_groupe: "" };
    const three: CompetitorContact = {
      ...entry,
      emergency_contacts: [
        { name: "A", phone: "01" },
        { name: "Sans numéro", phone: "" },
        { name: "C", phone: "03" },
      ],
      emergency1_name: "",
      emergency1_phone: "",
      emergency2_name: "",
      emergency2_phone: "",
    };
    const competition = {
      id: 1,
      nom: "Coupe",
      participants: [{ adherent_id: 2, nom: "X", prenom: "Y", urgence_nom: "Copie", urgence_tel: "0600" }],
    };
    const row = participantRows(competition, [], [three])[0]!;
    expect(row.emergency).toEqual([
      { name: "A", phone: "01" },
      { name: "C", phone: "03" },
    ]);
    expect(row.contacts.map((card) => card.title)).toEqual([
      "🧗 Athlète",
      "🚨 Contact d'urgence 1",
      "🚨 Contact d'urgence 2",
      "🚨 Contact d'urgence 3",
    ]);

    const saved: SavedCompetitorContact = {
      ...three,
      emergency_contacts: null,
      emergency1_name: "Ancien",
      emergency1_phone: "01",
      emergency2_name: "Autre",
      emergency2_phone: "02",
    };
    expect(participantRows(competition, [], [saved])[0]!.emergency).toEqual([
      { name: "Ancien", phone: "01" },
      { name: "Autre", phone: "02" },
    ]);
  });

  it("uses the copy made when the member was added only without a competitor entry", () => {
    const competition = {
      id: 1,
      nom: "Coupe",
      participants: [{ adherent_id: 2, nom: "X", prenom: "Y", urgence_nom: "Copie", urgence_tel: "0600" }],
    };
    expect(participantRows(competition, [], [])[0]!.contacts[1]).toMatchObject({ name: "Copie", phone: "0600" });
    const emptied: CompetitorContact = {
      adherent_id: 2,
      last_name: "",
      first_name: "",
      phone: "",
      creneau_groupe: "",
      emergency_contacts: [],
      emergency1_name: "",
      emergency1_phone: "",
      emergency2_name: "",
      emergency2_phone: "",
    };
    expect(participantRows(competition, [], [emptied])[0]!.emergency).toEqual([]);
  });

  it("handles empty or partial contacts gracefully", () => {
    const p = { nom: "SOLO", prenom: "Han" };
    const cards = athleteContactCards(p);
    expect(cards).toHaveLength(2);
    expect(cards[0]!.name).toBe("Han SOLO");
    expect(cards[0]!.phone).toBe("");
    expect(cards[0]!.email).toBe("");
    expect(cards[1]).toEqual({ role: "emergency", title: "🚨 Contact d'urgence", name: "", phone: "", email: "" });
  });
});
