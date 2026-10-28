import { afterEach, describe, expect, it, vi } from "vitest";
import type { Schemas } from "../../lib/client";
import {
  AGGREGATORS,
  clearLayout,
  DEFAULT_LAYOUT,
  LAYOUT_KEY,
  loadLayout,
  pivotRow,
  RENDERERS,
  restoreLayout,
  saveLayout,
  type PivotLayout,
} from "./pivotLayout";

const LAYOUT: PivotLayout = {
  rows: ["Ville"],
  cols: ["Tranche d'Âge"],
  vals: ["Nom"],
  aggregatorName: "% de la ligne",
  rendererName: "Carte de chaleur",
  rowOrder: "value_z_to_a",
  colOrder: "value_a_to_z",
};

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("restoreLayout", () => {
  it("keeps a valid layout", () => {
    expect(restoreLayout(JSON.stringify(LAYOUT))).toEqual(LAYOUT);
  });

  it.each([null, "", "{", "[]", "42", '"Tableau"', "null"])("falls back to the default for %j", (raw) => {
    expect(restoreLayout(raw)).toEqual(DEFAULT_LAYOUT);
  });

  it("drops what the table no longer knows", () => {
    const raw = JSON.stringify({
      rows: ["Ville", "Pointure", 3, "Ville"],
      cols: ["Ville", "Sexe"],
      vals: "Nom",
      aggregatorName: "Count",
      rendererName: "Grouped Column Chart",
      rowOrder: "random",
    });
    expect(restoreLayout(raw)).toEqual({
      ...DEFAULT_LAYOUT,
      rows: ["Ville"],
      cols: ["Sexe"], // a field is on one axis only
    });
  });

  it("keeps empty axes", () => {
    expect(restoreLayout(JSON.stringify({ ...LAYOUT, rows: [], cols: [] }))).toMatchObject({ rows: [], cols: [] });
  });
});

describe("stored layout", () => {
  it("is saved without the value filters, then read back", () => {
    const model = { ...LAYOUT, valueFilter: { Statut: { Annulé: true } } };
    saveLayout(model);
    expect(JSON.parse(localStorage.getItem(LAYOUT_KEY) ?? "")).toEqual(LAYOUT);
    expect(loadLayout()).toEqual(LAYOUT);
    clearLayout();
    expect(localStorage.getItem(LAYOUT_KEY)).toBeNull();
    expect(loadLayout()).toEqual(DEFAULT_LAYOUT);
  });

  it("falls back to the default when the storage fails", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    expect(loadLayout()).toEqual(DEFAULT_LAYOUT);
    expect(() => saveLayout(LAYOUT)).not.toThrow();
  });
});

describe("table options", () => {
  it("has the default aggregator and renderer", () => {
    expect(DEFAULT_LAYOUT.aggregatorName in AGGREGATORS).toBe(true);
    expect(DEFAULT_LAYOUT.rendererName in RENDERERS).toBe(true);
  });

  it("makes the unknown age a value of its own and labels the sex", () => {
    const record: Schemas["PivotRecord"] = {
      Nom: "WEASLEY",
      Prénom: "Ron",
      Sexe: "H",
      Âge: null,
      "Tranche d'Âge": "Inconnue",
      Ville: "Jonage",
      "Groupe / Tarif": "Loisir",
      Statut: "Validé",
      Saison: "2026-2027",
      "Type d'Adhésion": "Déjà Membre",
      "Date d'Inscription": "2026-06-03",
      "Mois d'Inscription": "2026-06",
    };
    expect(pivotRow(record).Âge).toBe("Inconnu");
    expect(pivotRow({ ...record, Âge: 12 }).Âge).toBe(12);
    expect(pivotRow(record).Sexe).toBe("Homme");
    expect(pivotRow({ ...record, Sexe: null }).Sexe).toBe("Non renseigné");
  });
});
