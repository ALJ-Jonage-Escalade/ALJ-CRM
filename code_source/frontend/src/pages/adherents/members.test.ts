import { describe, expect, it } from "vitest";
import {
  allowedTarifs,
  checkAll,
  creneauItems,
  csvName,
  csvRows,
  dateValue,
  diplomes,
  diplomeWeight,
  emptyFilters,
  filterMembers,
  loadFilters,
  matchesSearch,
  recordMember,
  recordQuery,
  saveFilters,
  shortenGroupLabel,
  statusChips,
  tarifCounts,
  type Creneau,
} from "./members";
import { member } from "./members.fixture";

const CRENEAUX: Creneau[] = [
  { groupe: "Loisir adultes", tarifs: ["Adulte loisir"], categorie_age: "", type: "" },
  { groupe: "Enfants 2015-2016 mercredi", tarifs: ["Enfant 2015"], categorie_age: "", type: "" },
  { groupe: "Enfants 2017-2018 samedi", tarifs: ["Enfant 2017"], categorie_age: "", type: "" },
  { groupe: "Compétition U13", tarifs: ["Compet U13"], categorie_age: "", type: "" },
  { groupe: "Liste d'attente collège", tarifs: ["Attente collège"], categorie_age: "", type: "" },
];

describe("slot filter", () => {
  it("groups the slots by section, Enfants by birth years, with short labels", () => {
    expect(creneauItems(CRENEAUX).map((it) => `${it.kind}:${it.label}`)).toEqual([
      "group:Loisir adultes",
      "section:Collège",
      "group:Liste d'attente",
      "section:Enfants",
      "sub:2015-2016",
      "group:mercredi",
      "sub:2017-2018",
      "group:samedi",
      "section:Compétition",
      "group:U13",
    ]);
    expect(shortenGroupLabel("Perfectionnement (ados)", "perfectionnement")).toBe("ados");
  });

  it("counts the members of each slot and of the tariffs no slot covers; waiting lists are left out by default", () => {
    const items = creneauItems(CRENEAUX);
    const members = [
      member({ tarif_name: "Adulte loisir" }),
      member({ tarif_name: "adulte LOISIR" }),
      member({ tarif_name: "Attente collège" }),
      member({ tarif_name: "Licence sèche" }),
      member({ tarif_name: "" }),
    ];
    const counts = tarifCounts(members, items);
    expect(counts.groups["Loisir adultes"]).toBe(2);
    expect(counts.others).toEqual({ "Licence sèche": 1 });

    const filters = emptyFilters();
    const allowed = allowedTarifs(items, counts, filters);
    expect(allowed.has("attente college")).toBe(false);
    // The member without a tariff stays listed
    expect(filterMembers(members, filters, allowed).map((m) => m.tarif_name)).toEqual([
      "Adulte loisir",
      "adulte LOISIR",
      "Licence sèche",
      "",
    ]);

    const none = checkAll(filters, items, counts, false);
    expect(filterMembers(members, none, allowedTarifs(items, counts, none))).toHaveLength(1);
    const every = checkAll(filters, items, counts, true);
    expect(filterMembers(members, every, allowedTarifs(items, counts, every))).toHaveLength(5);
    expect(filters.groups).toEqual({}); // checkAll returns new filters
  });
});

describe("search and status", () => {
  const m = member({
    last_name: "DUPONT",
    first_name: "Éloïse",
    city: "Villette d'Anthon",
    phone: "06 12 34 56 78",
    email_primary: "e.dupont@example.org",
    licence_ffme: "123456",
    tarif_name: "Adulte loisir",
    commentaires_correctif: "certificat à revoir",
  });

  it.each([
    ["dupont", true],
    ["eloise dupont", true],
    ["DUPONT ELOISE", true],
    ["villette", true],
    ["0612 3456", true],
    ["12 34", true],
    ["e.dupont@", true],
    ["123456", true],
    ["certificat", true],
    ["martin", false],
    ["", true],
  ])("search %j → %s", (q, found) => {
    expect(matchesSearch(m, q)).toBe(found);
  });

  it("filters on the status, and lists the statuses present with their counts", () => {
    const members = [member({ status_norm: "Validé" }), member({ status_norm: "Validé" }), member({ status_norm: "Annulé" })];
    expect(statusChips(members)).toEqual([
      { value: "", label: "Tous", count: 3 },
      { value: "Validé", label: "Validé", count: 2 },
      { value: "Annulé", label: "Annulé", count: 1 },
    ]);
    const filters = { ...emptyFilters(), status: "Annulé" };
    expect(filterMembers(members, filters, new Set())).toHaveLength(1);
  });
});

describe("display", () => {
  it("reads the diplomas and weighs them for sorting", () => {
    const m = member({
      badge_rouge: "Oui",
      autonomie_bloc: "x",
      raw_passports: "Passeport Orange escalade",
      key: { id: 4, code: "12", given_on: "2025-09-10" }, // a key is no diploma (Outils › Clés)
    });
    expect(diplomes(m).map((d) => d.icon)).toEqual(["🔴", "🧗", "🟠"]);
    expect(diplomeWeight(m)).toBe(7);
    expect(diplomeWeight(member({ autonomie_bloc: "non" }))).toBe(0);
  });

  it("compares ISO and French dates", () => {
    expect(dateValue("03/09/2026")).toBe(dateValue("2026-09-03"));
    expect(dateValue("")).toBe(0);
  });

  it("names the member record by member, season and membership", () => {
    expect(recordQuery(member({ user_id: 42, purchase_id: 7, season_name: "2025-2026" }))).toEqual({
      id: "42",
      saison: "2025-2026",
      achat: "7",
    });
    const both = [
      member({ user_id: 42, purchase_id: 7 }),
      member({ user_id: 42, purchase_id: 8 }),
      member({ user_id: 43, purchase_id: 9 }),
    ];
    expect(recordMember(both, "42", "8")?.purchase_id).toBe(8);
    expect(recordMember(both, "42")?.purchase_id).toBe(7); // a link of the former page: the first membership
    expect(recordMember(both, "44")).toBeUndefined();
  });
});

describe("CSV export", () => {
  it("has the columns of the former page, one row per member", () => {
    const rows = csvRows([
      member({
        last_name: "DUPONT",
        first_name: "Léa",
        birth_date: "2012-05-04",
        age: 14,
        ffme_category: "U15",
        amount: 180,
        order_date: "2026-09-01T12:00:00",
      }),
    ]);
    expect(rows[0]!.slice(0, 4)).toEqual(["Nom", "Prénom", "Date de naissance", "Âge"]);
    expect(rows[0]).toHaveLength(25);
    expect(rows[0]!.at(-1)).toBe("Date commande");
    expect(rows[1]!.slice(0, 4)).toEqual(["DUPONT", "Léa", "04/05/2012", 14]);
    expect(rows[1]![8]).toBe(180);
    expect([rows[0]![5], rows[1]![5]]).toEqual(["Catégorie", "U15"]);
    expect(rows[1]![24]).toBe("01/09/2026");
    expect(csvName("2026-2027")).toBe("adherents_2026-2027.csv");
  });

  it("adds columns for a third contact, none being lost", () => {
    const contact = (name: string) => ({ name, phone: `06 ${name}` });
    const rows = csvRows([
      member({ last_name: "A", emergency_contacts: [contact("1"), contact("2"), contact("3")] }),
      member({ last_name: "B", emergency_contacts: [contact("4")] }),
    ]);
    const firstContact = rows[0]!.indexOf("Urgence 1 - Nom");
    expect(rows[0]!.slice(firstContact, firstContact + 7)).toEqual([
      "Urgence 1 - Nom",
      "Urgence 1 - Tél",
      "Urgence 2 - Nom",
      "Urgence 2 - Tél",
      "Urgence 3 - Nom",
      "Urgence 3 - Tél",
      "Payeur",
    ]);
    expect(rows[1]!.slice(firstContact, firstContact + 6)).toEqual(["1", "06 1", "2", "06 2", "3", "06 3"]);
    expect(rows[2]!.slice(firstContact, firstContact + 6)).toEqual(["4", "06 4", "", "", "", ""]);
    expect(rows[1]).toHaveLength(rows[0]!.length);
  });
});

describe("saved filters", () => {
  it("keeps season, status and checked lines, never the search", () => {
    const store = new Map<string, string>();
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    saveFilters({ season: "2025-2026", status: "Validé", search: "dupont", groups: { "Loisir adultes": false }, others: {} }, storage);
    expect(loadFilters(storage)).toEqual({
      season: "2025-2026",
      status: "Validé",
      search: "",
      groups: { "Loisir adultes": false },
      others: {},
    });
  });

  it("falls back to the defaults on unreadable or blocked storage", () => {
    expect(loadFilters({ getItem: () => "{oops" })).toEqual(emptyFilters());
    expect(loadFilters({ getItem: () => JSON.stringify({ season: 3, groups: { a: "yes", b: true } }) })).toEqual({
      ...emptyFilters(),
      groups: { b: true },
    });
    expect(
      loadFilters({
        getItem: () => {
          throw new Error("blocked");
        },
      }),
    ).toEqual(emptyFilters());
    expect(() =>
      saveFilters(emptyFilters(), {
        setItem: () => {
          throw new Error("full");
        },
      }),
    ).not.toThrow();
  });
});
