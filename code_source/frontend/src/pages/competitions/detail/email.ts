/* E-mail to the competitors of a competition: the audience, a preview with the competition's variables (the server
   fills them again when sending: infrastructure/mail/dispatch.py get_competition_context), the request body. */
import type { Schemas } from "../../../lib/client";
import { looksLikeEmail } from "../../../lib/email";
import { formatDayText } from "../../../lib/format";
import { deadlineOf, type Competition, type Row } from "../competitions";

export type Template = Schemas["EmailTemplate"];
export type Audience = "selected" | "unpaid" | "all";

export const AUDIENCES: { id: Audience; label: string }[] = [
  { id: "selected", label: "Sélectionnés (Participe : Oui)" },
  { id: "unpaid", label: "Sélectionnés, paiement non reçu" },
  { id: "all", label: "Tous les inscrits de la liste" },
];

export function audience(rows: readonly Row[], who: Audience): Row[] {
  const known = rows.filter((r) => r.adherent_id != null);
  if (who === "selected") {
    return known.filter((r) => r.selectionne);
  }
  if (who === "unpaid") {
    return known.filter((r) => r.selectionne && r.statut_paiement !== "paye");
  }
  return known;
}

export const hasEmail = (r: Row): boolean => looksLikeEmail(r.email ?? "");

/** The template offered first: the club's « Compétition - 1er Inscription », else any about competitions, else the first. */
export function defaultTemplate(templates: readonly Template[]): Template | undefined {
  return (
    templates.find((t) => t.name === "Compétition - 1er Inscription") ??
    templates.find((t) => /comp[ée]tition/i.test(t.name)) ??
    templates[0]
  );
}

/** 15 -> « 15 », 15.5 -> « 15,50 » (domain/utils.format_amount). */
export function amountText(prix: number | null | undefined): string {
  if (prix == null) {
    return "";
  }
  const t = Number(prix).toFixed(2).replace(".", ",");
  return t.endsWith(",00") ? t.slice(0, -3) : t;
}

/** The WhatsApp link variable and its historical spellings (including the "whatapp" typo). */
const WHATSAPP_LINK_KEYS = ["whatsapp_link", "whatsapp_id", "whatapp_id", "whatapp_link"];

export function variables(c: Competition, r: Row | undefined): Record<string, string> {
  const start = formatDayText(c.date_competition ?? "");
  const end = formatDayText(c.date_fin ?? "");
  const whatsappLink = (c.whatsapp_link ?? "").trim();
  const dateFormatted = !end || end === start || !start ? start : `${start} au ${end}`;
  const deadlineFormatted = formatDayText(deadlineOf(c));
  const lieu = (c.lieu ?? "").trim();
  return {
    first_name: (r?.prenom ?? "").trim(),
    last_name: (r?.nom ?? "").trim().toUpperCase(),
    prenom: (r?.prenom ?? "").trim(),
    nom: (r?.nom ?? "").trim().toUpperCase(),
    num_licence: r?.num_licence ?? "",
    nom_competition: c.nom ?? "",
    name_competition: c.nom ?? "",
    competition_nom: c.nom ?? "",
    no_competition: c.id_ffme ?? "",
    montant_competition: amountText(c.prix),
    date_competition: dateFormatted,
    competition_date: dateFormatted,
    competition_deadline: deadlineFormatted,
    deadline: deadlineFormatted,
    lieu,
    competition_lieu: lieu,
    // Other spellings that saved templates may use (lower case: names are not case sensitive)
    ...Object.fromEntries(WHATSAPP_LINK_KEYS.map((key) => [key, whatsappLink])),
    bloc_whatsapp: whatsappLink ? `Voici le lien du groupe WhatsApp dédié à cette compétition : ${whatsappLink}` : "",
  };
}

/** The text with the values (variable names are not case sensitive; unknown ones are kept). */
export function render(text: string, values: Record<string, string>): string {
  return text.replace(/\{([^{}]+)\}/g, (whole, name: string) => values[name.toLowerCase()] ?? whole);
}

/** Body of POST /api/send-email; the server checks a coach writes to known members only. */
export function sendBody(c: Competition, recipients: readonly Row[], subject: string, body: string) {
  return {
    subject: subject.trim(),
    body: body.trim(),
    competition_id: c.id,
    recipients: recipients.filter(hasEmail).map((r) => ({
      id: r.adherent_id,
      first_name: r.prenom ?? "",
      last_name: r.nom ?? "",
      email: (r.email ?? "").trim(),
      num_licence: r.num_licence ?? "",
    })),
  };
}
