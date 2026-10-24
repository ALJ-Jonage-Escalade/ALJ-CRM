import { describe, expect, it } from "vitest";
import type { Competition, MemberSlot } from "./competitions";
import {
  displayName,
  filterItems,
  isIgnored,
  isLinked,
  itemCounts,
  itemInfo,
  stateLabel,
  suggestedCompetition,
  suggestedMember,
  syncMessage,
  type HelloAssoItem,
} from "./helloasso";

const RAW = {
  name: "Inscription compétition",
  state: "Processed",
  amount: 1500,
  user: { firstName: "Léo", lastName: "Martin" },
  payer: { firstName: "Paul", lastName: "Martin", email: "paul@x.fr", city: "Jonage", zipCode: "69330" },
  order: { id: 77, date: "2026-10-01T10:00:00+02:00", formName: "Compétitions 2026" },
  customFields: [
    { name: "Licence", answer: "123456" },
    { name: "Numéro de la compétition", value: "EVT-9" },
  ],
  payments: [{ id: 5, amount: 1500, state: "Authorized", paymentMeans: "Card" }],
};
const item = (change: Partial<HelloAssoItem>): HelloAssoItem => ({ id_item: 1, montant: 15, ...change });
const COMPS: Competition[] = [
  { id: 10, nom: "Coupe du Rhône", id_ffme: "EVT-9" },
  { id: 11, nom: "Open de Lyon" },
];
const MEMBERS: MemberSlot[] = [
  { id: 1, nom: "MARTIN", prenom: "Léo", licence_ffme: "123456" },
  { id: 2, nom: "DURAND", prenom: "Zoé" },
];

describe("helloasso", () => {
  it("reads the raw item, custom fields from answer or value", () => {
    const info = itemInfo(item({ raw_json: JSON.stringify(RAW), date_item: "" }));
    expect(info).toMatchObject({
      beneficiary: "Léo Martin",
      payerName: "Paul Martin",
      payerCity: "69330 Jonage",
      orderId: "77",
      itemName: "Inscription compétition",
      formName: "Compétitions 2026",
    });
    expect(info.fields).toEqual([
      { name: "Licence", answer: "123456" },
      { name: "Numéro de la compétition", answer: "EVT-9" },
    ]);
    expect(info.payments).toEqual([{ id: "5", amount: 15, state: "Authorized", date: "", means: "Card" }]);
    expect(info.date).toBe("2026-10-01T10:00:00+02:00");
    const bare = item({ raw_json: "not json", payer_prenom: "Zoé", payer_nom: "Durand" });
    expect([displayName(bare), itemInfo(bare).raw]).toEqual(["Zoé Durand", {}]);
    expect(displayName(item({}))).toBe("Article #1");
    expect(stateLabel("Processed")).toBe("Payé (Processed)");
  });

  it("counts, filters (ignored ones hidden from « all » on request), searches and sorts", () => {
    const items = [
      item({ id_item: 1, competition_id: 10, adherent_id: 1, date_item: "2026-10-03" }),
      item({ id_item: 2, ignore: true, ignore_motif: "Doublon", date_item: "2026-10-04" }),
      item({ id_item: 3, payer_nom: "Fletcher", date_item: "2026-10-01" }),
      item({ id_item: 4, payer_nom: "Lockhart", date_item: "2026-10-02" }),
      item({ id_item: 5, ignore: true, competition_id: 10, adherent_id: 2 }), // linked since: not ignored
    ];
    expect([isLinked(items[0]!), isIgnored(items[1]!), isIgnored(items[4]!)]).toEqual([true, true, false]);
    expect(itemCounts(items)).toEqual({ all: 5, linked: 2, ignored: 1, unlinked: 2 });
    const ids = (f: "unlinked" | "linked" | "ignored" | "all", hide = true, q = "") =>
      filterItems(items, f, hide, q, COMPS, MEMBERS).map((i) => i.id_item);
    expect(ids("unlinked")).toEqual([4, 3]);
    expect(ids("linked")).toEqual([1, 5]);
    expect(ids("ignored")).toEqual([2]);
    expect(ids("all")).toEqual([4, 3, 1, 5]);
    expect(ids("all", false)).toEqual([4, 3, 1, 5, 2]);
    expect(ids("all", false, "doublon")).toEqual([2]);
    expect(ids("all", true, "coupe du rhone")).toEqual([1, 5]); // by the linked competition's name
    expect(ids("all", true, "zoe")).toEqual([5]); // by the linked member's name
  });

  it("suggests the competition and the member from what the payer typed", () => {
    const typed = item({ raw_json: JSON.stringify(RAW) });
    expect(suggestedCompetition(typed, COMPS)).toBe(10); // FFME number in a custom field
    expect(suggestedMember(typed, MEMBERS)).toBe(1); // licence number
    expect(suggestedCompetition(item({ competition_saisie: "open de lyon 2026" }), COMPS)).toBe(11);
    expect(suggestedMember(item({ payer_nom: "Durand", payer_prenom: "Zoé" }), MEMBERS)).toBe(2);
    expect(suggestedMember(item({ adherent_id: 2, raw_json: JSON.stringify(RAW) }), MEMBERS)).toBe(2); // its link first
    expect([suggestedCompetition(item({}), COMPS), suggestedMember(item({}), MEMBERS)]).toEqual([null, null]);
  });

  it("words the sync outcome", () => {
    expect(syncMessage({ status: "success", stats: { nb_items: 3, nb_auto: 1, nb_manual: 0, nb_applied: 1, nb_unlinked: 2 } })).toBe(
      "✅ Synchro terminée : 3 article(s), 1 auto, 2 en attente.",
    );
    expect(syncMessage({ status: "error", message: "Aucune campagne" })).toBe("❌ Aucune campagne");
  });
});
