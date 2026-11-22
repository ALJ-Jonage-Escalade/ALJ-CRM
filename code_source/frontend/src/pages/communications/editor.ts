/* The e-mail template editor of the Communications page: checks before saving, live preview with a demo member,
   insertion of variables and HTML tags in the body (texts of the former web/bureau/communications.html). */
import type { EmailTemplate } from "../../services/communications";
import { looksLikeEmail } from "../../lib/email";
import { DEMO_VALUES, renderTemplate, templateError as variablesError } from "../../lib/templateVariables";

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

export const PREVIEW_TO = "Alex MARTIN <alex.martin@example.com>";

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
    subject: renderTemplate(template.subject, DEMO_VALUES) || "(Sans objet)",
    body: renderTemplate(template.body, DEMO_VALUES) || "(Message vide)",
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
  const unknown = variablesError([template.subject, template.body]);
  return unknown ? `⚠️ ${unknown}` : null;
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
