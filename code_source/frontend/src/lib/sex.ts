/* Labels of a member's FFME sex (`Schemas["Sex"]`, "F" / "H"): the only place they are written. */
import type { Schemas } from "./client";

export type Sex = Schemas["Sex"];

export const SEX_LABELS: Record<Sex, string> = { F: "Femme", H: "Homme" };
const SEX_PLURAL_LABELS: Record<Sex, string> = { F: "Femmes", H: "Hommes" };
export const SEX_NOT_GIVEN = "Non renseigné";

/** "Femme", "Homme" or "Non renseigné" (undefined: a list saved offline before the field existed). */
export function sexLabel(sex: Sex | null | undefined): string {
  return sex ? SEX_LABELS[sex] : SEX_NOT_GIVEN;
}

/** "Femmes", "Hommes" or "Non renseigné", for counts. */
export function sexPluralLabel(sex: Sex | null | undefined): string {
  return sex ? SEX_PLURAL_LABELS[sex] : SEX_NOT_GIVEN;
}
