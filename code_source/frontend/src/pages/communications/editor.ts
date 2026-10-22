/* The e-mail template editor of the Communications page: checks before saving, live preview with a demo member,
   insertion of variables and HTML tags in the body (texts of the former web/bureau/communications.html). */
import type { Schemas } from "../../lib/client";
import { looksLikeEmail } from "../../lib/email";

export type Template = Schemas["EmailTemplate"];

export const DEFAULT_SENDER_EMAIL = "inscription@alj-escalade.fr";
export const DEFAULT_SENDER_NAME = "Amicale Laïque Jonage - Inscriptions";
export const SENDER_SUGGESTIONS = ["inscription@alj-escalade.fr", "contact@alj-escalade.fr", "competitions@alj-escalade.fr", "admin@alj-escalade.fr"];

/** Contents of a new template; the sender is the one being edited. */
export function newTemplate(name: string, sender: Pick<Template, "sender_email" | "sender_name">): Template {
  return {
    name,
    subject: "Sujet du courriel",
    body: "Bonjour {first_name},\n\nSaisissez votre texte ici.\n\nSportivement,\nL'équipe ALJ Escalade",
    sender_email: sender.sender_email.trim() || DEFAULT_SENDER_EMAIL,
    sender_name: sender.sender_name.trim() || DEFAULT_SENDER_NAME,
  };
}

/** Variables replaced when the e-mail is sent (domain/utils.apply_template_variables), with the preview's values. */
export const DEMO_MEMBER: Record<string, string> = {
  first_name: "Alex",
  last_name: "MARTIN",
  tarif: "Cours Ados 2 (Mercredi 17h30)",
  season: "2026-2027",
  amount: "195.00 €",
  num_licence: "847291",
  nom_competition: "Championnat Régional Bloc",
  date_competition: "15/11/2026",
  montant_competition: "15.00 €",
};
export const VARIABLES = Object.keys(DEMO_MEMBER).map((name) => `{${name}}`);
export const PREVIEW_TO = "Alex MARTIN <alex.martin@example.com>";

// Former names of the first two variables, still found in old templates
const ALIASES: Record<string, string> = { prénom: DEMO_MEMBER.first_name!, nom: DEMO_MEMBER.last_name! };

/** The text as the demo member would receive it (variable names are not case sensitive). */
export function renderDemo(text: string): string {
  return text.replace(/\{([^{}]+)\}/g, (whole, name: string) => {
    const key = name.toLowerCase();
    return DEMO_MEMBER[key] ?? ALIASES[key] ?? whole;
  });
}

export interface Preview {
  from: string;
  subject: string;
  body: string;
}

export function preview(t: Template): Preview {
  const name = t.sender_name.trim() || DEFAULT_SENDER_NAME;
  const email = t.sender_email.trim() || DEFAULT_SENDER_EMAIL;
  return { from: `${name} <${email}>`, subject: renderDemo(t.subject) || "(Sans objet)", body: renderDemo(t.body) || "(Message vide)" };
}

/** Why the template cannot be saved, or null. */
export function templateError(t: Template): string | null {
  if (!t.name.trim()) return "⚠️ Le titre du modèle ne peut pas être vide.";
  if (!t.subject.trim() || !t.body.trim()) return "⚠️ Le sujet et le corps du message sont obligatoires.";
  if (!looksLikeEmail(t.sender_email.trim())) return "⚠️ L'adresse d'expédition doit être une adresse e-mail valide.";
  return null;
}

/** Why a new template cannot take this name, or null (the server checks again). */
export function newNameError(name: string, templates: readonly Template[]): string | null {
  if (!name) return "⚠️ Veuillez renseigner le nom du modèle.";
  const lower = name.toLowerCase();
  if (templates.some((t) => t.name.toLowerCase() === lower)) return `⚠️ Un modèle nommé « ${name} » existe déjà.`;
  return null;
}

/** The template shown first: the requested one, else the instalment reminder, else the first. */
export function initialTemplate(templates: readonly Template[], wanted?: string): Template | undefined {
  return templates.find((t) => t.name === wanted) ?? templates.find((t) => t.name.toLowerCase().includes("echeance")) ?? templates[0];
}

/** A text field after an edit, with the selection to restore. */
export interface Edit {
  value: string;
  start: number;
  end: number;
}

/** Replaces the selection with the text; the cursor goes after it. */
export function insertText(value: string, start: number, end: number, text: string): Edit {
  const at = start + text.length;
  return { value: value.slice(0, start) + text + value.slice(end), start: at, end: at };
}

/** Puts the tags around the selection ("texte" when nothing is selected), which stays selected. */
export function wrapSelection(value: string, start: number, end: number, open: string, close: string): Edit {
  const selected = value.slice(start, end) || "texte";
  const from = start + open.length;
  return { value: value.slice(0, start) + open + selected + close + value.slice(end), start: from, end: from + selected.length };
}

/** The link's address, or null for an empty answer (the prompt starts with "https://"). */
export function linkTarget(answer: string | null): string | null {
  const url = answer?.trim() ?? "";
  return url && url !== "https://" ? url : null;
}

/** Escapes the address for the href attribute. */
export function linkTags(url: string): [string, string] {
  return [`<a href="${url.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}">`, "</a>"];
}
