/* The e-mail template editor of the Communications page: checks before saving, live preview with a demo member,
   insertion of variables and HTML tags in the body (texts of the former web/bureau/communications.html). */
import type { EmailTemplate } from "../../services/communications";
import { looksLikeEmail } from "../../lib/email";
import { fillTemplate } from "../../lib/text";

/** The club's default sender, sent by the server (infrastructure/mail/senders.py). */
export type Sender = Pick<EmailTemplate, "sender_email" | "sender_name">;

/** Contents of a new template; the sender is the one being edited (empty: the server puts the club's default). */
export function newTemplate(name: string, sender: Sender): EmailTemplate {
  return {
    name,
    subject: "Sujet du courriel",
    body: "Bonjour {first_name},\n\nSaisissez votre texte ici.\n\nSportivement,\nL'équipe ALJ Escalade",
    sender_email: sender.sender_email.trim(),
    sender_name: sender.sender_name.trim(),
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
  competition_deadline: "08/11/2026",
  montant_competition: "15.00 €",
};
export const VARIABLES = Object.keys(DEMO_MEMBER).map((name) => `{${name}}`);
export const PREVIEW_TO = "Alex MARTIN <alex.martin@example.com>";

// Former names of the first two variables, still found in old templates
const ALIASES: Record<string, string> = { prénom: DEMO_MEMBER.first_name!, nom: DEMO_MEMBER.last_name! };

/** The values the preview fills a template with: the demo member, under the current and the former names. */
export const DEMO_VALUES: Readonly<Record<string, string>> = { ...ALIASES, ...DEMO_MEMBER };

export interface Preview {
  from: string;
  subject: string;
  body: string;
}

export function preview(template: EmailTemplate, defaultSender: Sender): Preview {
  const name = template.sender_name.trim() || defaultSender.sender_name;
  const email = template.sender_email.trim() || defaultSender.sender_email;
  return {
    from: `${name} <${email}>`,
    subject: fillTemplate(template.subject, DEMO_VALUES) || "(Sans objet)",
    body: fillTemplate(template.body, DEMO_VALUES) || "(Message vide)",
  };
}

/** Why the template cannot be saved, or null. */
export function templateError(template: EmailTemplate): string | null {
  if (!template.name.trim()) {
    return "⚠️ Le titre du modèle ne peut pas être vide.";
  }
  if (!template.subject.trim() || !template.body.trim()) {
    return "⚠️ Le sujet et le corps du message sont obligatoires.";
  }
  if (!looksLikeEmail(template.sender_email.trim())) {
    return "⚠️ L'adresse d'expédition doit être une adresse e-mail valide.";
  }
  return null;
}

/** Why a new template cannot take this name, or null (the server checks again). */
export function newNameError(name: string, templates: readonly EmailTemplate[]): string | null {
  if (!name) {
    return "⚠️ Veuillez renseigner le nom du modèle.";
  }
  const lower = name.toLowerCase();
  if (templates.some((t) => t.name.toLowerCase() === lower)) {
    return `⚠️ Un modèle nommé « ${name} » existe déjà.`;
  }
  return null;
}

/** The template shown first: the requested one, else the instalment reminder, else the first. */
export function initialTemplate(templates: readonly EmailTemplate[], wanted?: string): EmailTemplate | undefined {
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
