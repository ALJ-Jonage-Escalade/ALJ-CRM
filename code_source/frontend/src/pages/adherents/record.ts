/* Member record of Adhérents: what the record shows, the edit / add form (draft, checks, changes sent), the e-mail and
   the payment certificate (texts of the former web/bureau/adherents.html). Writes and sends are for admins; the server
   checks the role and the fields again (api/members/schemas.py). */
import type { EmailTemplate } from "../../services/communications";
import type { Schemas } from "../../lib/client";
import { looksLikeEmail } from "../../lib/email";
import { emergencyContactsOf } from "../../lib/emergencyContacts";
import { formatDate, formatDayText } from "../../lib/format";
import { COUNTRY_CHOICES, knownChoice, NATIONALITY_CHOICES } from "../../lib/countries";
import { PASSPORT_COLOURS, passportMarks } from "../../lib/passports";
import { SEX_LABELS, sexLabel, type Sex } from "../../lib/sex";
import { normKey } from "../../lib/text";
import { amountText, firstNameText, lastNameText, type VariableKey } from "../../lib/templateVariables";
import type { MemberStatus } from "../../services/members";
import { diplomes, isYes, STATUSES, type Creneau, type Member } from "./members";

export type MemberChanges = Schemas["MemberChanges"];
export type NewMember = Schemas["NewMember"];

// ---------------------------------------------------------------- Record

export interface RecordRow {
  icon: string;
  label: string;
  value: string;
  /** The value links there (in the app). */
  to?: string;
}

/** Lines of the record, empty ones left out. */
export function recordRows(member: Member): RecordRow[] {
  const rows: RecordRow[] = [];
  const add = (icon: string, label: string, value: string) => {
    if (value) {
      rows.push({ icon, label, value });
    }
  };
  const join = (sep: string, ...parts: string[]) => parts.filter(Boolean).join(sep);
  add(
    "🎂",
    "Date de naissance",
    member.birth_date ? `${formatDayText(member.birth_date)}${member.age != null ? ` (${member.age} ans)` : ""}` : "",
  );
  add("⚧", "Sexe", member.sex ? SEX_LABELS[member.sex] : "");
  add("📍", "Adresse", join(", ", member.address, join(" ", member.zip_code, member.city)));
  add("🌍", "Pays", member.country ?? "");
  add("🪪", "Nationalité", member.nationality ?? "");
  add("📞", "Téléphone", member.phone);
  add("✉️", "E-mail principal", member.email_primary);
  add("✉️", "E-mail secondaire", member.email_secondary);
  add("🪪", "Licence FFME", member.licence_ffme);
  emergencyContactsOf(member).forEach((contact, index) => add("🚨", `Urgence ${index + 1}`, join(" · ", contact.name, contact.phone)));
  add(
    "🩺",
    "Santé & Engagement",
    join(
      " · ",
      member.health_commitment && `engagement : ${member.health_commitment}`,
      member.document_sante && `document : ${member.document_sante}`,
    ),
  );
  add("📷", "Droit à l'image", member.photo_auth);
  add("🔴", "Badge rouge", member.badge_rouge);
  add("🧗", "Autonomie bloc", member.autonomie_bloc);
  if (member.key) {
    // Held keys are managed in Outils › Clés (plans/club-keys.md): the line opens the key there
    rows.push({
      icon: "🔑",
      label: "Clé de la salle",
      value: `n° ${member.key.code} depuis le ${formatDayText(member.key.given_on)}`,
      to: `/bureau/outils/cles?cle=${member.key.id}`,
    });
  }
  if (diplomes(member).some((d) => d.type === "passeport_orange")) {
    add(PASSPORT_COLOURS.orange, "Passeport orange", "Oui");
  }
  const passportCircles = passportMarks(member.raw_passports);
  add(
    "🎓",
    "Passeports FFME",
    passportCircles === member.raw_passports ? member.raw_passports : `${passportCircles} ${member.raw_passports}`,
  );
  if (member.payer && normKey(member.payer) !== normKey(`${member.first_name} ${member.last_name}`)) {
    add("💳", "Payeur", member.payer + (member.payer_email ? ` (${member.payer_email})` : ""));
  }
  add("🧾", "Commande HelloAsso", join(" · ", formatDayText(member.order_date), member.order_ref));
  add("💶", "Montant réglé", member.amount != null ? `${member.amount} €` : "");
  add("📧", "Attestation envoyée", member.email_sent_date ? formatDayText(member.email_sent_date) : "");
  add(
    "🧗",
    "Créneau",
    member.creneau_groupe ? `${member.creneau_groupe}${member.creneau_details ? ` (${member.creneau_details})` : ""}` : "",
  );
  add("💬", "Commentaire", member.commentaires_correctif);
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
    if (t && (!detail.has(t) || (!detail.get(t) && text))) {
      detail.set(t, text);
    }
  };
  for (const c of creneaux) {
    for (const t of c.tarifs) {
      add(t, c.groupe);
    }
  }
  for (const m of members) {
    add(m.tarif_name, [m.creneau_groupe, m.creneau_details].filter(Boolean).join(" · "));
  }
  add("Licence sèche", "Licence seule · Sans créneau de cours");
  return [...detail].map(([tarif, text]) => ({ tarif, detail: text })).sort((a, b) => a.tarif.localeCompare(b.tarif, "fr"));
}

// ---------------------------------------------------------------- Actions on a record (MemberActionsDialog)

export type RecordAction = "edit" | "email" | "attestation";

/** What MemberActionsDialog exposes to the page. */
export interface RecordActions {
  open(action: RecordAction): Promise<void>;
}

// ---------------------------------------------------------------- Edit / add form

export const STATUS_CHOICES = [
  ["Validé", "🟢 Validé"],
  ["Traité", "🔵 Traité"],
  ["En cours", "🟠 En cours / En attente"],
  ["Terminé", "🟣 Terminé"],
  ["Annulé", "🔴 Annulé"],
] as const satisfies readonly (readonly [MemberStatus, string])[];

/** A row of the contact list as typed. key: local identity of the row, so moving it keeps its inputs and focus. */
export interface ContactRow {
  key: number;
  name: string;
  phone: string;
}

let lastContactKey = 0;

/** A blank row of the contact list. */
export function newContactRow(name = "", phone = ""): ContactRow {
  lastContactKey += 1;
  return { key: lastContactKey, name, phone };
}

/** Values of the form, as typed. All fields can be edited or filled when adding. */
export interface MemberDraft {
  last_name: string;
  first_name: string;
  birth_date: string;
  /** Empty: not given (never guessed, the FFME export leaves a new member without it out) */
  sex: Sex | "";
  /** One of STATUS_CHOICES, or the member's own status when it is none of them (kept unless changed). */
  status: string;
  amount: string;
  tarif_name: string;
  licence_ffme: string;
  badge_rouge: "Oui" | "Non";
  autonomie_bloc: "Oui" | "Non";
  photo_auth: "Oui" | "Non";
  email_primary: string;
  email_secondary: string;
  phone: string;
  address: string;
  zip_code: string;
  city: string;
  /** A choice of COUNTRY_CHOICES, or the stored value the FFME export does not recognise (kept unless changed). */
  country: string;
  /** A choice of NATIONALITY_CHOICES, or the stored value the FFME export does not recognise (kept unless changed). */
  nationality: string;
  /** In order, the first one is the main one; blank rows are not sent. */
  emergency_contacts: ContactRow[];
  commentaires_correctif: string;
}

export type TextField = Exclude<keyof MemberDraft, "emergency_contacts">;
/** A field that can get an error: a text field, or the phone of a contact row. */
export type DraftField = TextField | `contact_phone_${number}`;
export const contactPhoneField = (key: number): DraftField => `contact_phone_${key}`;
export type DraftErrors = Partial<Record<DraftField, string>>;

/** The form of an existing member, or of a new one (first tariff chosen, as before). */
export function draftOf(member?: Member, firstTarif = ""): MemberDraft {
  const contacts = member ? emergencyContactsOf(member) : [];
  return {
    last_name: member?.last_name ?? "",
    first_name: member?.first_name ?? "",
    birth_date: member?.birth_date ?? "",
    sex: member?.sex ?? "",
    status: member?.status_norm || "Validé",
    amount: member ? (member.amount != null ? String(member.amount) : "") : "0.00",
    tarif_name: member ? member.tarif_name : firstTarif,
    licence_ffme: member?.licence_ffme ?? "",
    badge_rouge: member && isYes(member.badge_rouge) ? "Oui" : "Non",
    autonomie_bloc: member && isYes(member.autonomie_bloc) ? "Oui" : "Non",
    photo_auth: member ? (isYes(member.photo_auth) ? "Oui" : "Non") : "Oui",
    email_primary: member?.email_primary ?? "",
    email_secondary: member?.email_secondary ?? "",
    phone: member?.phone ?? "",
    address: member?.address ?? "",
    zip_code: member?.zip_code ?? "",
    city: member?.city ?? "",
    // A list saved offline before the fields existed has none
    country: member ? (member.country ?? "") : "France",
    nationality: member ? (member.nationality ?? "") : "Française",
    emergency_contacts: contacts.length ? contacts.map((contact) => newContactRow(contact.name, contact.phone)) : [newContactRow()],
    commentaires_correctif: member?.commentaires_correctif ?? "",
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
  if (!m) {
    return false;
  }
  const d = new Date(+m[1]!, +m[2]! - 1, +m[3]!);
  return d.getMonth() === +m[2]! - 1 && d.getDate() === +m[3]! && d <= today && +m[1]! >= 1900;
}

const PHONE_FIELDS = ["phone"] as const satisfies readonly TextField[];
const EMAIL_FIELDS = ["email_primary", "email_secondary"] as const satisfies readonly TextField[];

/** Problems of the form, by field (empty when it can be sent). adding: the add form, which asks more. amountBefore:
    the amount the edit form opened with (the server keeps an amount once set: it cannot be emptied). */
export function draftErrors(draft: MemberDraft, adding: boolean, today: Date = new Date(), amountBefore = ""): DraftErrors {
  const errors: DraftErrors = {};
  if (!draft.last_name.trim()) {
    errors.last_name = "Le nom est obligatoire.";
  }
  if (!draft.first_name.trim()) {
    errors.first_name = "Le prénom est obligatoire.";
  }
  if (adding && !draft.birth_date) {
    errors.birth_date = "La date de naissance est obligatoire.";
  } else if (draft.birth_date && !validBirthDate(draft.birth_date, today)) {
    errors.birth_date = "Date de naissance invalide.";
  }
  const amount = Number(draft.amount.replace(",", "."));
  if (draft.amount.trim() && (!Number.isFinite(amount) || amount < 0)) {
    errors.amount = "Montant invalide (nombre positif).";
  } else if (!adding && amountBefore.trim() && !draft.amount.trim()) {
    errors.amount = "Le montant ne peut pas être vidé : indiquez 0 si rien n'a été réglé.";
  }
  for (const contact of draft.emergency_contacts) {
    if (contact.phone.trim() && !looksLikePhone(contact.phone.trim())) {
      errors[contactPhoneField(contact.key)] = "Numéro de téléphone invalide.";
    }
  }
  if (!draft.tarif_name.trim()) {
    errors.tarif_name = "Choisissez un groupe (tarif).";
  }
  for (const field of PHONE_FIELDS) {
    if (draft[field].trim() && !looksLikePhone(draft[field].trim())) {
      errors[field] = "Numéro de téléphone invalide.";
    }
  }
  for (const field of EMAIL_FIELDS) {
    if (draft[field].trim() && !looksLikeEmail(draft[field].trim())) {
      errors[field] = "Adresse e-mail invalide.";
    }
  }
  return errors;
}

/** The rows to send: trimmed, without their local key, blank ones left out. */
function contactsToSend(rows: readonly ContactRow[]): Schemas["EmergencyContact"][] {
  return rows.map((row) => ({ name: row.name.trim(), phone: row.phone.trim() })).filter((row) => row.name || row.phone);
}

/** The new member sent to /api/members/create. */
export function newMemberOf(draft: MemberDraft): NewMember {
  return {
    last_name: draft.last_name.trim().toUpperCase(),
    first_name: draft.first_name.trim(),
    birth_date: draft.birth_date,
    sex: draft.sex || null,
    tarif_name: draft.tarif_name.trim(),
    // The add form offers STATUS_CHOICES only; anything else leaves the server default
    status: STATUSES.find((status) => status === draft.status),
    amount: Number(draft.amount.replace(",", ".")) || 0,
    licence_ffme: draft.licence_ffme.trim(),
    badge_rouge: draft.badge_rouge,
    autonomie_bloc: draft.autonomie_bloc,
    photo_auth: draft.photo_auth,
    email_primary: draft.email_primary.trim(),
    email_secondary: draft.email_secondary.trim(),
    phone: draft.phone.trim(),
    address: draft.address.trim(),
    zip_code: draft.zip_code.trim(),
    city: draft.city.trim(),
    country: knownChoice(COUNTRY_CHOICES, draft.country),
    nationality: knownChoice(NATIONALITY_CHOICES, draft.nationality),
    emergency_contacts: contactsToSend(draft.emergency_contacts),
    commentaires_correctif: draft.commentaires_correctif.trim(),
  };
}

export interface Changes {
  fields: MemberChanges;
  /** One line per change, for the confirmation. */
  lines: string[];
}

const EDITED: [keyof MemberChanges & TextField, string][] = [
  ["last_name", "Nom"],
  ["first_name", "Prénom"],
  ["birth_date", "Date de naissance"],
  ["status", "Statut"],
  ["licence_ffme", "Licence FFME"],
  ["badge_rouge", "Badge rouge"],
  ["autonomie_bloc", "Autonomie bloc"],
  ["photo_auth", "Droit à l'image"],
  ["email_primary", "E-mail principal"],
  ["email_secondary", "E-mail secondaire"],
  ["phone", "Téléphone"],
  ["address", "Adresse"],
  ["zip_code", "Code postal"],
  ["city", "Ville"],
  ["country", "Pays"],
  ["nationality", "Nationalité"],
  ["tarif_name", "Créneau / Tarif"],
];

const contactsLine = (contacts: readonly Schemas["EmergencyContact"][]): string =>
  contacts.map((contact) => [contact.name, contact.phone].filter(Boolean).join(" · ")).join(" ; ") || "vide";

/** What the edit form changes on the member (only those fields are sent). */
export function changesOf(member: Member, draft: MemberDraft): Changes {
  const before = draftOf(member);
  const fields: MemberChanges = {};
  const lines: string[] = [];
  for (const [field, label] of EDITED) {
    const was = before[field].trim();
    const now = field === "last_name" ? draft.last_name.trim().toUpperCase() : draft[field].trim();
    if (now === was) {
      continue;
    }
    (fields as Record<string, string | number | null>)[field] = now;
    lines.push(`${label} : ${was || "vide"} ➔ ${now || "vide"}`);
  }
  const contactsWas = contactsToSend(before.emergency_contacts);
  const contactsNow = contactsToSend(draft.emergency_contacts);
  if (JSON.stringify(contactsNow) !== JSON.stringify(contactsWas)) {
    fields.emergency_contacts = contactsNow;
    lines.push(`Contacts d'urgence : ${contactsLine(contactsWas)} ➔ ${contactsLine(contactsNow)}`);
  }
  const amountBefore = member.amount != null ? member.amount : null;
  const amountTrimmed = draft.amount.trim();
  const amountNow = amountTrimmed !== "" ? Number(amountTrimmed.replace(",", ".")) : null;
  if (amountNow !== null && Number.isFinite(amountNow) && amountNow !== amountBefore) {
    fields.amount = amountNow;
    lines.push(`Montant : ${amountBefore != null ? `${amountBefore} €` : "vide"} ➔ ${amountNow} €`);
  }
  const sexWas = member.sex ?? null;
  const sexNow = draft.sex || null;
  if (sexNow !== sexWas) {
    fields.sex = sexNow;
    lines.push(`Sexe : ${sexLabel(sexWas)} ➔ ${sexLabel(sexNow)}`);
  }
  const was = member.commentaires_correctif.trim();
  const now = draft.commentaires_correctif.trim();
  if (now !== was) {
    fields.commentaires_correctif = now;
    lines.push(now ? (was ? "Commentaire mis à jour" : "Commentaire ajouté") : "Commentaire effacé");
  }
  return { fields, lines };
}

/** Another member of the season with the same name (asked before adding). */
export function sameName(members: readonly Member[], draft: MemberDraft): Member | undefined {
  const last = normKey(draft.last_name);
  const first = normKey(draft.first_name);
  return members.find((m) => normKey(m.last_name) === last && normKey(m.first_name) === first);
}

/** The comment with today's date at the start of a new line: "[22/10/2026] ". */
export function withDateTag(comment: string, today: Date = new Date()): string {
  const tag = `[${formatDate(today)}] `;
  return comment && !comment.endsWith("\n") ? `${comment}\n${tag}` : comment + tag;
}

// ---------------------------------------------------------------- E-mail and certificate

/** Values of the template variables for the member, as the server fills them (domain/email_personalization.py). */
export function memberVariables(member: Member): Record<VariableKey, string> {
  return {
    first_name: firstNameText(member.first_name),
    last_name: lastNameText(member.last_name),
    num_licence: member.licence_ffme,
    tarif: member.tarif_name,
    season: member.season_name,
    amount: amountText(member.amount),
    problemes: "",
    name_competition: "",
    no_competition: "",
    date_competition: "",
    montant_competition: "",
    whatsapp_link: "",
  };
}

/** Signature shown in the preview; the address comes from the server (empty if the templates could not be loaded, e.g. offline). */
export function signatureText(clubContactEmail: string): string {
  return `ALJ Escalade — Section de l'Amicale Laïque de Jonage\n${clubContactEmail}`.trim();
}

/** Default template of the certificate e-mail, when the club has none named « échéance » (the server picks the sender). */
export const DEFAULT_ATTESTATION_TEMPLATE: EmailTemplate = {
  name: "Attestation échéance",
  subject: "Attestation de paiement et d'échéance - Amicale Laïque de Jonage",
  body: "Bonjour {first_name},\n\nNous avons le plaisir de vous transmettre en pièce jointe l'attestation de paiement pour votre adhésion ou celle de votre enfant à la section escalade de l'Amicale Laïque de Jonage.\n\nSportivement,\nL'équipe ALJ Escalade",
  sender_email: "",
  sender_name: "",
};

/** Templates offered for the certificate e-mail, the « échéance » one first chosen. */
export function attestationTemplates(templates: readonly EmailTemplate[]): { list: EmailTemplate[]; initial: EmailTemplate } {
  const isEcheance = (t: EmailTemplate) => normKey(t.name).includes("echeance");
  const list = templates.some(isEcheance) ? [...templates] : [DEFAULT_ATTESTATION_TEMPLATE, ...templates];
  return { list, initial: list.find(isEcheance) ?? list[0]! };
}

/** Why no certificate can be made for this membership, or null (the server checks again). */
export function attestationProblem(member: Member): string | null {
  if (normKey(member.status_norm).includes("annul")) {
    return "la commande est annulée";
  }
  if (!(Number(member.amount) > 0)) {
    return "le montant est nul (0 €)";
  }
  return null;
}

/** Where the certificate goes by default: the payer, else the member. */
export function attestationRecipient(member: Member): string {
  return member.payer_email.trim() || member.email_primary.trim();
}

/** File name of the downloaded certificate: Attestation_DUPONT_Lea.pdf. */
export function attestationFileName(member: Member): string {
  const clean = (s: string) =>
    s
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^\w-]+/g, "_");
  const first = member.first_name ? member.first_name.charAt(0).toUpperCase() + member.first_name.slice(1).toLowerCase() : "Adherent";
  return `Attestation_${clean(member.last_name.toUpperCase() || "ADHERENT")}_${clean(first)}.pdf`;
}
