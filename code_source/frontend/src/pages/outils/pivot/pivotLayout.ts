/* Pivot table of the Outils page (vue-pivottable): the fields, the French aggregators and renderers, the default
   layout and the layout kept in localStorage (fields, aggregator, renderer, orders; never the value filters, which
   name values of a season). */
import { PivotUtilities, Renderer } from "vue-pivottable";
import { h, useAttrs, type Component, type VNode } from "vue";
import { localStorageOrNone } from "../../../lib/localStorage";
import type { Schemas } from "../../../lib/client";
import { sexLabel } from "../../../lib/sex";

type PivotRecord = Schemas["PivotRecord"];
export type PivotField = keyof PivotRecord;
/** A row of the table: the unknown age is a value of its own (filterable, skipped by the age aggregators); the sex
    is shown by its label, « Non renseigné » included. */
export type PivotRow = { [F in PivotField]: F extends "Âge" ? number | "Inconnu" : F extends "Sexe" ? string : PivotRecord[F] };

export const FIELDS = [
  "Nom",
  "Prénom",
  "Sexe",
  "Âge",
  "Tranche d'Âge",
  "Ville",
  "Groupe / Tarif",
  "Statut",
  "Saison",
  "Type d'Adhésion",
  "Date d'Inscription",
  "Mois d'Inscription",
] as const satisfies readonly PivotField[];

/** The row of the table for a record of the API. */
export function pivotRow(record: PivotRecord): PivotRow {
  return { ...record, Âge: record.Âge ?? "Inconnu", Sexe: sexLabel(record.Sexe) };
}

const { aggregatorTemplates: templates, numberFormat } = PivotUtilities;
type AggregatorTemplate = ReturnType<typeof templates.count>;

const THOUSANDS = " ";
const integer = numberFormat({ digitsAfterDecimal: 0, thousandsSep: THOUSANDS });
const decimal = numberFormat({ digitsAfterDecimal: 1, thousandsSep: THOUSANDS, decimalSep: "," });
const percent = numberFormat({ digitsAfterDecimal: 1, scaler: 100, suffix: " %", thousandsSep: THOUSANDS, decimalSep: "," });

/** The age aggregators read « Âge » themselves: no field to choose. */
const onAge =
  (template: AggregatorTemplate): AggregatorTemplate =>
  () =>
    template(["Âge"]);

export const AGGREGATORS: Record<string, AggregatorTemplate> = {
  Effectif: templates.count(integer),
  "% du total": templates.fractionOf(templates.count(), "total", percent),
  "% de la ligne": templates.fractionOf(templates.count(), "row", percent),
  "% de la colonne": templates.fractionOf(templates.count(), "col", percent),
  "Valeurs distinctes": templates.countUnique(integer),
  "Âge moyen": onAge(templates.average(decimal)),
  "Âge min": onAge(templates.min(integer)),
  "Âge max": onAge(templates.max(integer)),
};

const LOCALE_STRINGS = PivotUtilities.locales.fr?.localeStrings;

/** A renderer of the package under a French name. vue-pivottable 1.4.1 hands the table the whole language pack where
   it reads the « Totaux » label from the strings of the locale: the strings are passed instead. */
function renderer(name: string, base: string): { name: string; inheritAttrs: false; setup: () => () => VNode } {
  const component: Component | undefined = Renderer[base];
  if (!component) {
    throw new Error(`vue-pivottable sans le rendu « ${base} »`);
  }
  return {
    name,
    inheritAttrs: false,
    setup: () => {
      const attrs = useAttrs(); // every prop of the table: the renderer declares none
      return () => h(component, { ...attrs, languagePack: LOCALE_STRINGS });
    },
  };
}

export const RENDERERS = {
  Tableau: renderer("AljPivotTable", "Table"),
  "Carte de chaleur": renderer("AljPivotHeatmap", "Table Heatmap"),
  "Carte de chaleur par ligne": renderer("AljPivotRowHeatmap", "Table Row Heatmap"),
  "Carte de chaleur par colonne": renderer("AljPivotColHeatmap", "Table Col Heatmap"),
  "Export (copier vers Excel)": renderer("AljPivotTsv", "Export Table TSV"),
};

const ORDERS = ["key_a_to_z", "value_a_to_z", "value_z_to_a"] as const;
type Order = (typeof ORDERS)[number];

/** What the user arranges and what is kept between visits. */
export interface PivotLayout {
  rows: string[];
  cols: string[];
  vals: string[];
  aggregatorName: string;
  rendererName: string;
  rowOrder: Order;
  colOrder: Order;
}

/** Excluded values per field (vue-pivottable's valueFilter). */
export type ValueFilter = Record<string, Record<string, boolean>>;
export type PivotModel = PivotLayout & { valueFilter: ValueFilter };

export const DEFAULT_LAYOUT: Readonly<PivotLayout> = {
  rows: ["Groupe / Tarif"],
  cols: ["Statut", "Sexe"],
  vals: [],
  aggregatorName: "Effectif",
  rendererName: "Tableau",
  rowOrder: "key_a_to_z",
  colOrder: "key_a_to_z",
};

/** The values hidden at each visit and season change: the course waiting list and the cancelled memberships. */
export function defaultValueFilter(): ValueFilter {
  return { "Groupe / Tarif": { "Liste d'attente cours": true }, Statut: { Annulé: true } };
}

export function defaultModel(): PivotModel {
  return { ...structuredClone(DEFAULT_LAYOUT), valueFilter: defaultValueFilter() };
}

export const PIVOT_LAYOUT_STORAGE = "alj.pivot.layout.v1";

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isField = (value: unknown): value is PivotField => FIELDS.some((f) => f === value);
const isOrder = (value: unknown): value is Order => ORDERS.some((o) => o === value);

function fields(value: unknown, fallback: readonly string[], taken: readonly string[] = []): string[] {
  if (!Array.isArray(value)) {
    return [...fallback];
  }
  return [...new Set(value.filter(isField))].filter((f) => !taken.includes(f));
}

/** The stored layout (JSON) checked against what the table knows; anything unreadable falls back to the default. */
export function restoreLayout(raw: string | null): PivotLayout {
  let stored: unknown = null;
  try {
    stored = raw ? JSON.parse(raw) : null;
  } catch {
    stored = null;
  }
  if (!isRecord(stored)) {
    return structuredClone(DEFAULT_LAYOUT);
  }
  const rows = fields(stored.rows, DEFAULT_LAYOUT.rows);
  const { aggregatorName, rendererName, rowOrder, colOrder } = stored;
  return {
    rows,
    cols: fields(stored.cols, DEFAULT_LAYOUT.cols, rows),
    vals: fields(stored.vals, DEFAULT_LAYOUT.vals),
    aggregatorName: typeof aggregatorName === "string" && aggregatorName in AGGREGATORS ? aggregatorName : DEFAULT_LAYOUT.aggregatorName,
    rendererName: typeof rendererName === "string" && rendererName in RENDERERS ? rendererName : DEFAULT_LAYOUT.rendererName,
    rowOrder: isOrder(rowOrder) ? rowOrder : DEFAULT_LAYOUT.rowOrder,
    colOrder: isOrder(colOrder) ? colOrder : DEFAULT_LAYOUT.colOrder,
  };
}

/** The part of the model that is stored: never the value filters. */
export function layoutOf(model: PivotLayout): PivotLayout {
  const { rows, cols, vals, aggregatorName, rendererName, rowOrder, colOrder } = model;
  return { rows: [...rows], cols: [...cols], vals: [...vals], aggregatorName, rendererName, rowOrder, colOrder };
}

export function loadLayout(): PivotLayout {
  try {
    return restoreLayout(localStorageOrNone()?.getItem(PIVOT_LAYOUT_STORAGE) ?? null);
  } catch {
    return structuredClone(DEFAULT_LAYOUT);
  }
}

export function saveLayout(model: PivotLayout): void {
  try {
    localStorageOrNone()?.setItem(PIVOT_LAYOUT_STORAGE, JSON.stringify(layoutOf(model)));
  } catch (e) {
    console.warn("Disposition du TCD non enregistrée :", e);
  }
}

export function clearLayout(): void {
  try {
    localStorageOrNone()?.removeItem(PIVOT_LAYOUT_STORAGE);
  } catch (e) {
    console.warn("Disposition du TCD non effacée :", e);
  }
}
