/* The {…} variables of the e-mail templates, as the server handles them (domain/email_variables.py): their French
   label, the template kinds that may use them, their demo value, and the rendering of a text with values. The previews
   render here, instantly and offline; templateVariables.golden.json holds the cases both sides must agree on. */
import type { Schemas } from "./client";
import { normKey } from "./text";

export type VariableKey = Schemas["EmailVariable"]["key"];
export type TemplateKind = Schemas["EmailVariable"]["kinds"][number];
export type TemplateVariable = Schemas["EmailVariable"];
/** The value of each variable; a missing one renders as nothing. */
export type VariableValues = Readonly<Partial<Record<VariableKey, string>>>;

const ALL_KINDS: TemplateKind[] = ["adherent", "attestation", "competition"];

/** Every variable of the server: a key added there and not here fails the typecheck. */
const VARIABLES: Record<VariableKey, Omit<TemplateVariable, "key" | "aliases">> = {
  first_name: { label: "Prénom", kinds: ALL_KINDS, demo: "Alex" },
  last_name: { label: "Nom", kinds: ALL_KINDS, demo: "MARTIN" },
  num_licence: { label: "N° de licence", kinds: ALL_KINDS, demo: "847291" },
  tarif: { label: "Tarif", kinds: ALL_KINDS, demo: "Cours Ados 2 (Mercredi 17h30)" },
  season: { label: "Saison", kinds: ALL_KINDS, demo: "2026-2027" },
  amount: { label: "Montant de l'adhésion", kinds: ["adherent", "attestation"], demo: "195" },
  problemes: { label: "Problèmes à corriger", kinds: ["adherent"], demo: "- Date de naissance manquante" },
  name_competition: { label: "Nom de la compétition", kinds: ["competition"], demo: "Championnat Régional Bloc" },
  no_competition: { label: "N° de la compétition", kinds: ["competition"], demo: "2026-RA-0142" },
  date_competition: { label: "Date de la compétition", kinds: ["competition"], demo: "15/11/2026" },
  montant_competition: { label: "Montant de la compétition", kinds: ["competition"], demo: "15,50" },
  whatsapp_link: { label: "Lien WhatsApp", kinds: ["competition"], demo: "https://chat.whatsapp.com/demo" },
};

/** The variable whose line goes away when it is empty. */
const REMOVES_LINE_WHEN_EMPTY: readonly VariableKey[] = ["whatsapp_link"];

const WHATSAPP_SENTENCE = "Voici le lien du groupe WhatsApp dédié à cette compétition : {whatsapp_link}";
/** Former spellings of saved templates, with the text they stand for (in keys). */
const ALIASES: Readonly<Record<string, string>> = {
  nom_competition: "{name_competition}",
  whatapp_id: "{whatsapp_link}",
  whatsapp_id: "{whatsapp_link}",
  whatapp_link: "{whatsapp_link}",
  bloc_whatsapp: WHATSAPP_SENTENCE,
  bloc_whatapp: WHATSAPP_SENTENCE,
  whatsapp_bloc: WHATSAPP_SENTENCE,
};

const isVariableKey = (key: string): key is VariableKey => Object.hasOwn(VARIABLES, key);
const KEYS = Object.keys(VARIABLES).filter(isVariableKey);

/** The variables, in the server's order, with their former spellings. */
export const TEMPLATE_VARIABLES: readonly TemplateVariable[] = KEYS.map((key) => ({
  key,
  ...VARIABLES[key],
  aliases: Object.entries(ALIASES)
    .filter(([, text]) => text.includes(`{${key}}`))
    .map(([alias]) => alias),
}));

/** The values of the previews. */
export const DEMO_VALUES: Readonly<Record<VariableKey, string>> = Object.fromEntries(
  KEYS.map((key) => [key, VARIABLES[key].demo]),
) as Record<VariableKey, string>;

/** `{…}` without `<`, `>`, `"` or line break inside: HTML and links are never taken for a variable. */
const TOKEN = /\{([^{}<>"\r\n]+)\}/g;

/** How a name is compared: case, accents, dashes and extra spaces do not matter (domain/utils.normalize_name). */
function fold(name: string): string {
  return normKey(name).replace(/-/g, " ").split(/\s+/).filter(Boolean).join(" ");
}

const BY_NAME = new Map<string, VariableKey>(
  KEYS.flatMap((key) => [[fold(key), key] as const, [fold(VARIABLES[key].label), key] as const]),
);
const ALIASES_BY_NAME = new Map(Object.entries(ALIASES).map(([alias, text]) => [fold(alias), text]));

/** The variable a token's name stands for (its key or its label, leniently). */
export function findVariable(name: string): VariableKey | undefined {
  return BY_NAME.get(fold(name));
}

/** The text with each former spelling replaced by the text it stands for. */
export function expandAliases(text: string): string {
  return text.replace(TOKEN, (whole, name: string) => ALIASES_BY_NAME.get(fold(name)) ?? whole);
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
}

/** The text with each known variable replaced by its value (nothing when empty), as the server sends it; the line of
    an empty WhatsApp link goes away; unknown tokens are kept. `html`: values escaped, their line breaks as <br>. */
export function renderTemplate(text: string, values: VariableValues, options: { html?: boolean } = {}): string {
  const valueOf = (key: VariableKey): string => (values[key] ?? "").trim();
  const isDropped = (line: string): boolean =>
    [...line.matchAll(TOKEN)].some((match) => {
      const key = findVariable(match[1] ?? "");
      return key !== undefined && REMOVES_LINE_WHEN_EMPTY.includes(key) && !valueOf(key);
    });
  const lines = expandAliases(text).split(/(?<=\n)/);
  const kept = lines.filter((line) => !isDropped(line));
  const joined = kept.length === lines.length ? kept.join("") : kept.join("").replace(/\n{3,}/g, "\n\n");
  return joined.replace(TOKEN, (whole, name: string) => {
    const key = findVariable(name);
    if (key === undefined) {
      return whole;
    }
    const value = valueOf(key);
    return options.html ? escapeHtml(value).replace(/\n/g, "<br>\n") : value;
  });
}

/** 15 -> « 15 », 15.5 -> « 15,50 », no currency sign (domain/utils.format_amount). */
export function amountText(amount: number | string | null | undefined): string {
  if (amount == null || (typeof amount === "string" && !amount.trim())) {
    return "";
  }
  const value = Number(amount);
  if (!Number.isFinite(value)) {
    return "";
  }
  const text = value.toFixed(2).replace(".", ",");
  return text.endsWith(",00") ? text.slice(0, -3) : text;
}

/** A first name as the e-mails write it: « Jean-Pierre » (Python's str.title()). */
export function firstNameText(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/(^|[^\p{L}])(\p{L})/gu, (_, before: string, letter: string) => before + letter.toUpperCase());
}

/** A last name as the e-mails write it: « DE LA TOUR ». */
export function lastNameText(name: string): string {
  return name.trim().toUpperCase();
}
