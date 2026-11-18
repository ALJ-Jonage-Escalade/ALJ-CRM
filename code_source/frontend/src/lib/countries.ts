/* Country and nationality choices of the member form: the table of the FFME export (server
   domain/members/countries.py), received as enums of the API contract. France / Française come first. */
import type { Schemas } from "./client";

export type CountryName = Exclude<NonNullable<Schemas["MemberChanges"]["country"]>, "">;
export type NationalityName = Exclude<NonNullable<Schemas["MemberChanges"]["nationality"]>, "">;

/** Each country of the table and its nationality: typed by the contract, so the build fails when the server adds or
    removes a country and this list is not updated. */
const NATIONALITY_OF: Record<CountryName, NationalityName> = {
  France: "Française",
  "Afrique du Sud": "Sud-africaine",
  Algérie: "Algérienne",
  Allemagne: "Allemande",
  Andorre: "Andorrane",
  Argentine: "Argentine",
  Australie: "Australienne",
  Autriche: "Autrichienne",
  Belgique: "Belge",
  Brésil: "Brésilienne",
  Bulgarie: "Bulgare",
  Canada: "Canadienne",
  Chili: "Chilienne",
  Chine: "Chinoise",
  "Côte d'Ivoire": "Ivoirienne",
  Croatie: "Croate",
  Danemark: "Danoise",
  Espagne: "Espagnole",
  "États-Unis": "Américaine",
  Finlande: "Finlandaise",
  Grèce: "Grecque",
  Hongrie: "Hongroise",
  Inde: "Indienne",
  Irlande: "Irlandaise",
  Italie: "Italienne",
  Japon: "Japonaise",
  Luxembourg: "Luxembourgeoise",
  Maroc: "Marocaine",
  Mexique: "Mexicaine",
  Monaco: "Monégasque",
  Norvège: "Norvégienne",
  "Nouvelle-Zélande": "Néo-zélandaise",
  "Pays-Bas": "Néerlandaise",
  Pologne: "Polonaise",
  Portugal: "Portugaise",
  Roumanie: "Roumaine",
  "Royaume-Uni": "Britannique",
  Russie: "Russe",
  Sénégal: "Sénégalaise",
  Suède: "Suédoise",
  Suisse: "Suisse",
  Tchéquie: "Tchèque",
  Tunisie: "Tunisienne",
  Turquie: "Turque",
  Ukraine: "Ukrainienne",
  Vietnam: "Vietnamienne",
};

function isCountryName(value: string): value is CountryName {
  return Object.hasOwn(NATIONALITY_OF, value);
}

export const COUNTRY_CHOICES: readonly CountryName[] = Object.keys(NATIONALITY_OF).filter(isCountryName);
export const NATIONALITY_CHOICES: readonly NationalityName[] = Object.values(NATIONALITY_OF);

/** The value when it is one of the choices the server accepts, else "". */
export function knownChoice<T extends string>(choices: readonly T[], value: string): T | "" {
  return choices.find((choice) => choice === value) ?? "";
}

/** The options of a select, with the stored value first when it is none of the choices (a HelloAsso typo, shown so
    that the office sees it and picks the right one). */
export function choicesWith(choices: readonly string[], stored: string): { value: string; text: string }[] {
  const options = choices.map((choice) => ({ value: choice, text: choice }));
  return stored && !choices.some((choice) => choice === stored)
    ? [{ value: stored, text: `${stored} (non reconnu)` }, ...options]
    : options;
}
