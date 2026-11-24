/* The e-mail templates a send screen offers: those of its kind, the kind's default opened first. */
import type { EmailTemplate } from "../services/communications";
import type { Schemas } from "./client";
import type { TemplateKind } from "./templateVariables";

export function templatesOfKind(templates: readonly EmailTemplate[], kind: TemplateKind): EmailTemplate[] {
  return templates.filter((template) => template.kind === kind);
}

/** The template a screen opens first: its kind's default, else what the screen's own rule picks among its templates
    (the name rules used before templates had a default). */
export function initialOfKind(
  templates: readonly EmailTemplate[],
  kind: TemplateKind,
  fallback: (offered: readonly EmailTemplate[]) => EmailTemplate | undefined,
): EmailTemplate | undefined {
  const offered = templatesOfKind(templates, kind);
  return offered.find((template) => template.is_default) ?? fallback(offered);
}

/** Who a send request leaves from: a template's sender (the server reads it from the saved template), else the
    address chosen for the free text (empty: the sending account). Never both: the server refuses it. */
export function senderFields(
  template: EmailTemplate | undefined,
  senderEmail: string,
): Pick<Schemas["EmailSendRequest"], "template_name" | "sender_email"> {
  return template ? { template_name: template.name } : { sender_email: senderEmail };
}
