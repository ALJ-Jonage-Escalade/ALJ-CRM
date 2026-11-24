/* The e-mail template editor of the Communications page: checks before saving, live preview with a demo member,
   insertion of variables and HTML tags in the body (texts of the former web/bureau/communications.html). */
import type { EmailTemplate } from "../../services/communications";
import { DEMO_VALUES, renderHtml, renderTemplate, templateError as variablesError, type TemplateKind } from "../../lib/templateVariables";

/** The default sender, sent by the server: the sending account and the club's display name. */
export type Sender = Pick<EmailTemplate, "sender_email" | "sender_name">;

/** Contents of a new template; the sender and kind are those of the template being edited (an empty sender: the
    sending account). */
export function newTemplate(name: string, sender: Sender, kind: TemplateKind = "adherent"): EmailTemplate {
  return {
    name,
    kind,
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
  /** HTML, as the e-mail's HTML part (renderHtml): safe to show with v-html. */
  body: string;
}

export function preview(template: EmailTemplate, defaultSender: Sender): Preview {
  const name = template.sender_name.trim() || defaultSender.sender_name;
  const email = template.sender_email.trim() || defaultSender.sender_email;
  return {
    from: `${name} <${email}>`,
    subject: renderTemplate(template.subject, DEMO_VALUES) || "(Sans objet)",
    body: renderHtml(template.body, DEMO_VALUES) || "(Message vide)",
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
  const unknown = variablesError([template.subject, template.body], template.kind);
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
