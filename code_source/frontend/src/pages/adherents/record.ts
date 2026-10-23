/* Member record of Adhérents: what the record shows, the edit / add form (draft, checks, changes sent), the e-mail and
   the payment certificate (texts of the former web/bureau/adherents.html). Writes and sends are for admins; the server
   checks the role and the fields again (api/members/schemas.py). */
import type { Schemas } from "../../lib/client";
import { looksLikeEmail } from "../../lib/email";
import { diplomes, fmtDay, normKey, type Creneau, type Member } from "./members";

export type MemberChanges = Schemas["MemberChanges"];
export type NewMember = Schemas["NewMember"];
export type Template = Schemas["EmailTemplate"];

// ---------------------------------------------------------------- Record

export interface RecordRow {
  icon: string;
  label: string;
  value: string;
}

/** Lines of the record, empty ones left out. */
export function recordRows(m: Member): RecordRow[] {
  const rows: RecordRow[] = [];
  const add = (icon: string, label: string, value: string) => {
    if (value) rows.push({ icon, label, value });
  };
  const join = (sep: string, ...parts: string[]) => parts.filter(Boolean).join(sep);
  add("🎂", "Date de naissance", m.birth_date ? `${fmtDay(m.birth_date)}${m.age != null ? ` (${m.age} ans)` : ""}` : "");
  add("⚧", "Sexe", m.gender);
  add("📍", "Adresse", join(", ", m.address, join(" ", m.zip_code, m.city)));
  add("📞", "Téléphone", m.phone);
  add("✉️", "E-mail principal", m.email_primary);
  add("✉️", "E-mail secondaire", m.email_secondary);
  add("🪪", "Licence FFME", m.licence_ffme);
  add("🚨", "Urgence 1", join(" · ", m.emergency1_name, m.emergency1_phone));
  add("🚨", "Urgence 2", join(" · ", m.emergency2_name, m.emergency2_phone));
  add("🩺", "Santé & Engagement", join(" · ", m.health_commitment && `engagement : ${m.health_commitment}`, m.document_sante && `document : ${m.document_sante}`));
  add("📷", "Droit à l'image", m.photo_auth);
  add("🔴", "Badge rouge", m.badge_rouge);
  add("🧗", "Autonomie bloc", m.autonomie_bloc);
  if (diplomes(m).some((d) => d.type === "passeport_orange")) add("🟠", "Passeport orange", "Oui");
  add("🎓", "Passeports FFME", m.raw_passports);
  if (m.payer && normKey(m.payer) !== normKey(`${m.first_name} ${m.last_name}`)) {
    add("💳", "Payeur", m.payer + (m.payer_email ? ` (${m.payer_email})` : ""));
  }
  add("🧾", "Commande HelloAsso", join(" · ", fmtDay(m.order_date), m.order_ref));
  add("💶", "Montant réglé", m.amount != null ? `${m.amount} €` : "");
  add("📧", "Attestation envoyée", m.email_sent_date ? fmtDay(m.email_sent_date) : "");
  add("🧗", "Créneau", m.creneau_groupe ? `${m.creneau_groupe}${m.creneau_details ? ` (${m.creneau_details})` : ""}` : "");
  add("💬", "Commentaire", m.commentaires_correctif);
  return rows;
}

// ---------------------------------------------------------------- Tariffs of the form

export interface TarifChoice {
  tarif: string;
  /** Slot group and its day / hours, when known. */
  detail: string;
}

/** Tariffs a member can be put in: those of the planning's slots and those the season's members have, plus the
    licence without slot; sorted by name. */
export function tarifChoices(creneaux: readonly Creneau[], members: readonly Member[]): TarifChoice[] {
  const detail = new Map<string, string>();
  const add = (tarif: string, text: string) => {
    const t = tarif.trim();
    if (t && (!detail.has(t) || (!detail.get(t) && text))) detail.set(t, text);
  };
  for (const c of creneaux) for (const t of c.tarifs) add(t, c.groupe);
  for (const m of members) add(m.tarif_name, [m.creneau_groupe, m.creneau_details].filter(Boolean).join(" · "));
  add("Licence sèche", "Licence seule · Sans créneau de cours");
  return [...detail].map(([tarif, text]) => ({ tarif, detail: text })).sort((a, b) => a.tarif.localeCompare(b.tarif, "fr"));
}

// ---------------------------------------------------------------- Edit / add form

export const STATUS_CHOICES = [
  ["Validé", "🟢 Validé"],
  ["Traité", "🔵 Traité"],
  ["En cours", "🟠 En cours / En attente"],
  ["Terminé", "🟣 Terminé"],
  ["Annulé", "🔴 Annulé"],
] as const;

/** Values of the form, as typed. Identity, birth, amount and emergency contact are only asked when adding. */
export interface MemberDraft {
  last_name: string;
  first_name: string;
  birth_date: string;
  gender: "Homme" | "Femme";
  /** One of STATUS_CHOICES, or the member's own status when it is none of them (kept unless changed). */
  status: string;
  amount: string;
  tarif_name: string;
  licence_ffme: string;
  badge_rouge: "Oui" | "Non";
  autonomie_bloc: "Oui" | "Non";
  email_primary: string;
  email_secondary: string;
  phone: string;
  address: string;
  zip_code: string;
  city: string;
  emergency1_name: string;
  emergency1_phone: string;
  commentaires_correctif: string;
}

export type DraftField = keyof MemberDraft;
export type DraftErrors = Partial<Record<DraftField, string>>;

const yes = (v: string) => ["oui", "x", "true", "1"].includes(v.trim().toLowerCase());

/** The form of an existing member, or of a new one (first tariff chosen, as before). */
export function draftOf(m?: Member, firstTarif = ""): MemberDraft {
  return {
    last_name: m?.last_name ?? "",
    first_name: m?.first_name ?? "",
    birth_date: "",
    gender: m?.gender === "Femme" ? "Femme" : "Homme",
    status: m?.status_norm || "Validé",
    amount: "0.00",
    tarif_name: m ? m.tarif_name : firstTarif,
    licence_ffme: m?.licence_ffme ?? "",
    badge_rouge: m && yes(m.badge_rouge) ? "Oui" : "Non",
    autonomie_bloc: m && yes(m.autonomie_bloc) ? "Oui" : "Non",
    email_primary: m?.email_primary ?? "",
    email_secondary: m?.email_secondary ?? "",
    phone: m?.phone ?? "",
    address: m?.address ?? "",
    zip_code: m?.zip_code ?? "",
    city: m?.city ?? "",
    emergency1_name: "",
    emergency1_phone: "",
    commentaires_correctif: m?.commentaires_correctif ?? "",
  };
}

/** A phone number: digits (8 to 15), spaces, dots, dashes, brackets and a leading +. */
function looksLikePhone(value: string): boolean {
  const digits = value.replace(/\D/g, "").length;
  return /^\+?[\d\s.()-]+$/.test(value) && digits >= 8 && digits <= 15;
}

/** A yyyy-mm-dd date that exists, not in the future. */
function validBirthDate(value: string, today: Date): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return false;
  const d = new Date(+m[1]!, +m[2]! - 1, +m[3]!);
  return d.getMonth() === +m[2]! - 1 && d.getDate() === +m[3]! && d <= today && +m[1]! >= 1900;
}

/** Problems of the form, by field (empty when it can be sent). adding: the add form, which asks more. */
export function draftErrors(d: MemberDraft, adding: boolean, today: Date = new Date()): DraftErrors {
  const errors: DraftErrors = {};
  if (adding) {
    if (!d.last_name.trim()) errors.last_name = "Le nom est obligatoire.";
    if (!d.first_name.trim()) errors.first_name = "Le prénom est obligatoire.";
    if (!d.birth_date) errors.birth_date = "La date de naissance est obligatoire.";
    else if (!validBirthDate(d.birth_date, today)) errors.birth_date = "Date de naissance invalide.";
    const amount = Number(d.amount.replace(",", "."));
    if (d.amount.trim() && (!Number.isFinite(amount) || amount < 0)) errors.amount = "Montant invalide (nombre positif).";
    if (d.emergency1_phone.trim() && !looksLikePhone(d.emergency1_phone.trim())) errors.emergency1_phone = "Numéro de téléphone invalide.";
  }
  if (!d.tarif_name.trim()) errors.tarif_name = "Choisissez un groupe (tarif).";
  for (const field of ["email_primary", "email_secondary"] as const) {
    if (d[field].trim() && !looksLikeEmail(d[field].trim())) errors[field] = "Adresse e-mail invalide.";
  }
  if (d.phone.trim() && !looksLikePhone(d.phone.trim())) errors.phone = "Numéro de téléphone invalide.";
  return errors;
}

/** The new member sent to /api/members/create. */
export function newMemberOf(d: MemberDraft): NewMember {
  return {
    last_name: d.last_name.trim().toUpperCase(),
    first_name: d.first_name.trim(),
    birth_date: d.birth_date,
    gender: d.gender,
    tarif_name: d.tarif_name.trim(),
    status: d.status as NewMember["status"],  // the add form offers STATUS_CHOICES only
    amount: Number(d.amount.replace(",", ".")) || 0,
    licence_ffme: d.licence_ffme.trim(),
    badge_rouge: d.badge_rouge,
    autonomie_bloc: d.autonomie_bloc,
    email_primary: d.email_primary.trim(),
    email_secondary: d.email_secondary.trim(),
    phone: d.phone.trim(),
    address: d.address.trim(),
    zip_code: d.zip_code.trim(),
    city: d.city.trim(),
    emergency1_name: d.emergency1_name.trim(),
    emergency1_phone: d.emergency1_phone.trim(),
    commentaires_correctif: d.commentaires_correctif.trim(),
  };
}

export interface Changes {
  fields: MemberChanges;
  /** One line per change, for the confirmation. */
  lines: string[];
}

const EDITED: [keyof MemberChanges & DraftField, string][] = [
  ["status", "Statut"],
  ["licence_ffme", "Licence FFME"],
  ["badge_rouge", "Badge rouge"],
  ["autonomie_bloc", "Autonomie bloc"],
  ["email_primary", "E-mail principal"],
  ["email_secondary", "E-mail secondaire"],
  ["phone", "Téléphone"],
  ["address", "Adresse"],
  ["zip_code", "Code postal"],
  ["city", "Ville"],
  ["tarif_name", "Créneau / Tarif"],
];

/** What the edit form changes on the member (only those fields are sent). */
export function changesOf(m: Member, d: MemberDraft): Changes {
  const before = draftOf(m);
  const fields: Record<string, string> = {};
  const lines: string[] = [];
  for (const [field, label] of EDITED) {
    const was = before[field].trim();
    const now = d[field].trim();
    if (now === was) continue;
    fields[field] = now;
    lines.push(`${label} : ${was || "vide"} ➔ ${now || "vide"}`);
  }
  const was = m.commentaires_correctif.trim();
  const now = d.commentaires_correctif.trim();
  if (now !== was) {
    fields.commentaires_correctif = now;
    lines.push(now ? (was ? "Commentaire mis à jour" : "Commentaire ajouté") : "Commentaire effacé");
  }
  return { fields: fields as MemberChanges, lines };
}

/** Another member of the season with the same name (asked before adding). */
export function sameName(members: readonly Member[], d: MemberDraft): Member | undefined {
  const last = normKey(d.last_name);
  const first = normKey(d.first_name);
  return members.find((m) => normKey(m.last_name) === last && normKey(m.first_name) === first);
}

/** The comment with today's date at the start of a new line: "[22/10/2026] ". */
export function withDateTag(comment: string, today: Date = new Date()): string {
  const tag = `[${new Intl.DateTimeFormat("fr-FR").format(today)}] `;
  return comment && !comment.endsWith("\n") ? `${comment}\n${tag}` : comment + tag;
}

// ---------------------------------------------------------------- E-mail and certificate

/** Values of the template variables for the member (domain/utils.apply_template_variables). */
export function memberVariables(m: Member): Record<string, string> {
  const first = m.first_name.toLowerCase().replace(/(^|[\s\-'’])(\p{L})/gu, (_, sep: string, l: string) => sep + l.toUpperCase());
  const last = m.last_name.toUpperCase();
  return {
    first_name: first, last_name: last, prénom: first, nom: last,
    num_licence: m.licence_ffme, tarif: m.tarif_name, season: m.season_name, saison: m.season_name,
    amount: m.amount != null ? `${m.amount} €` : "", montant: m.amount != null ? `${m.amount} €` : "",
  };
}

/** The text with the member's values (variable names are not case sensitive; unknown ones are kept). */
export function renderFor(text: string, m: Member): string {
  const values = memberVariables(m);
  return text.replace(/\{([^{}]+)\}/g, (whole, name: string) => values[name.toLowerCase()] ?? whole);
}

export const SIGNATURE_TEXT = "ALJ Escalade — Section de l'Amicale Laïque de Jonage\ncontact@alj-escalade.fr";

/** Default template of the certificate e-mail, when the club has none named « échéance ». */
export const DEFAULT_ATTESTATION_TEMPLATE: Template = {
  name: "Attestation échéance",
  subject: "Attestation de paiement et d'échéance - Amicale Laïque de Jonage",
  body: "Bonjour {first_name},\n\nNous avons le plaisir de vous transmettre en pièce jointe l'attestation de paiement pour votre adhésion ou celle de votre enfant à la section escalade de l'Amicale Laïque de Jonage.\n\nSportivement,\nL'équipe ALJ Escalade",
  sender_email: "inscription@alj-escalade.fr",
  sender_name: "Amicale Laïque Jonage - Inscriptions",
};

/** Templates offered for the certificate e-mail, the « échéance » one first chosen. */
export function attestationTemplates(templates: readonly Template[]): { list: Template[]; initial: Template } {
  const isEcheance = (t: Template) => normKey(t.name).includes("echeance");
  const list = templates.some(isEcheance) ? [...templates] : [DEFAULT_ATTESTATION_TEMPLATE, ...templates];
  return { list, initial: list.find(isEcheance) ?? list[0]! };
}

/** Why no certificate can be made for this membership, or null (the server checks again). */
export function attestationProblem(m: Member): string | null {
  if (normKey(m.status_norm).includes("annul")) return "la commande est annulée";
  if (!(Number(m.amount) > 0)) return "le montant est nul (0 €)";
  return null;
}

/** Where the certificate goes by default: the payer, else the member. */
export function attestationRecipient(m: Member): string {
  return m.payer_email.trim() || m.email_primary.trim();
}

/** File name of the downloaded certificate: Attestation_DUPONT_Lea.pdf. */
export function attestationFileName(m: Member): string {
  const clean = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^\w-]+/g, "_");
  const first = m.first_name ? m.first_name.charAt(0).toUpperCase() + m.first_name.slice(1).toLowerCase() : "Adherent";
  return `Attestation_${clean(m.last_name.toUpperCase() || "ADHERENT")}_${clean(first)}.pdf`;
}
