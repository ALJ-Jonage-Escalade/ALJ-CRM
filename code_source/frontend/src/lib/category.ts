/* Labels of a member's FFME competition category (`Schemas["Category"]`, "U11" … "VETERAN_2"): the only place they are written. */
import type { Schemas } from "./client";
import type { Sex } from "./sex";

export type Category = Schemas["Category"];

export const CATEGORY_LABELS: Record<Category, string> = {
  U11: "U11",
  U13: "U13",
  U15: "U15",
  U17: "U17",
  U19: "U19",
  SENIOR: "Sénior",
  VETERAN_1: "Vétéran 1",
  VETERAN_2: "Vétéran 2",
};

/** The choice of no category (under 9, or set by hand). */
export const NO_CATEGORY = "Aucune";

/** Youngest first, the order of the lists. */
export const CATEGORY_ORDER: readonly Category[] = ["U11", "U13", "U15", "U17", "U19", "SENIOR", "VETERAN_1", "VETERAN_2"];

/** "U13", "Sénior"…; "" without a category ("" or undefined: a copy saved before the field existed). */
export function categoryLabel(category: Category | "" | null | undefined): string {
  return category ? CATEGORY_LABELS[category] : "";
}

/** "U13 F", the category competitors start in; the category alone when the sex is not known, "" without a category. */
export function categoryAndSexLabel(category: Category | "" | null | undefined, sex: Sex | null | undefined): string {
  const label = categoryLabel(category);
  return label && sex ? `${label} ${sex}` : label;
}
