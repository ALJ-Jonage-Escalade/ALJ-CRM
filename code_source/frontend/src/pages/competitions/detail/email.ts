/* E-mail to the competitors of a competition: the audience, a preview with the competition's variables (the server
   fills them again when sending: services/communications/email_dispatch.py get_competition_context), the request body. */
import type { EmailTemplate } from "../../../services/communications";
import type { Schemas } from "../../../lib/client";
import { looksLikeEmail } from "../../../lib/email";
import { formatDayText } from "../../../lib/format";
import { amountText, firstNameText, lastNameText, type VariableKey } from "../../../lib/templateVariables";
import { deadlineOf, type Competition, type Row } from "../competitions";

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

export const hasEmail = (row: Row): boolean => looksLikeEmail(row.email ?? "");

/** The competition template offered first when none is the default: the club's « Compétition - 1er Inscription »,
    else the first. */
export function defaultTemplate(templates: readonly EmailTemplate[]): EmailTemplate | undefined {
  return templates.find((t) => t.name === "Compétition - 1er Inscription") ?? templates[0];
}

/** Values of the template variables for a competitor, as the server fills them (services/communications/email_dispatch.py). */
export function variables(competition: Competition, row: Row | undefined): Record<VariableKey, string> {
  const start = formatDayText(competition.date_competition ?? "");
  const end = formatDayText(competition.date_fin ?? "");
  return {
    first_name: firstNameText(row?.prenom ?? ""),
    last_name: lastNameText(row?.nom ?? ""),
    num_licence: row?.num_licence ?? "",
    tarif: "",
    season: "",
    amount: "",
    problemes: "",
    name_competition: competition.nom ?? "",
    no_competition: competition.id_ffme ?? "",
    date_competition: !end || end === start || !start ? start : `${start} au ${end}`,
    competition_deadline: formatDayText(deadlineOf(competition)),
    montant_competition: amountText(competition.prix),
    whatsapp_link: (competition.whatsapp_link ?? "").trim(),
  };
}

/** Body of POST /api/send-email; the server checks a coach writes to known members only. `sender`: the template's
    name or the free text's sender (senderFields). */
export function sendBody(
  competition: Competition,
  recipients: readonly Row[],
  subject: string,
  body: string,
  sender: Pick<Schemas["EmailSendRequest"], "template_name" | "sender_email">,
): Schemas["EmailSendRequest"] {
  return {
    ...sender,
    subject: subject.trim(),
    body: body.trim(),
    competition_id: competition.id,
    recipients: recipients.filter(hasEmail).map((r) => ({
      id: r.adherent_id,
      first_name: r.prenom ?? "",
      last_name: r.nom ?? "",
      email: (r.email ?? "").trim(),
      num_licence: r.num_licence ?? "",
    })),
  };
}

/** The toast after a send; says when the send is missing from the e-mail history (the dates shown are then incomplete). */
export function sentMessage(result: Pick<Schemas["EmailDispatch"], "sent_count" | "errors_count" | "log_notice">): string {
  const failures = result.errors_count ? `, ${result.errors_count} en échec` : "";
  const notice = result.log_notice ? " ⚠️ Envoyé, mais non enregistré dans l'historique." : "";
  return `✅ ${result.sent_count} e-mail(s) envoyé(s) avec succès${failures}.${notice}`;
}
