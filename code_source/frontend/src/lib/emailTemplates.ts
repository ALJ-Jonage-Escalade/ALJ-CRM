/* The e-mail templates a send screen offers: those of its kind, the kind's default opened first. */
import type { EmailTemplate } from "../services/communications";
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
