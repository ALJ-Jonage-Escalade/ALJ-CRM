/* Import of the HelloAsso membership campaign (server: api/members/helloasso_import.py): the server sorts every
   registration of the campaign into a bucket; the preview shows one section per bucket. */
import type { BadgeColor } from "../../components/ui/palette";
import type { Schemas } from "../../lib/client";
import { formatDateTime, formatDayText, parseDate } from "../../lib/format";
import { normKey } from "../adherents/members";

export type MembershipPreview = Schemas["MembershipPreview"];
export type MembershipRow = Schemas["MembershipRow"];
export type BucketName = MembershipRow["bucket"];
export type MembershipImportResult = Schemas["MembershipImportResult"];

export interface BucketInfo {
  name: BucketName;
  label: string;
  color: BadgeColor;
}

/** The buckets, in the order of the preview. */
export const BUCKETS: readonly BucketInfo[] = [
  { name: "new", label: "🆕 Nouveaux", color: "green" },
  { name: "renewal", label: "🔁 Renouvellements", color: "blue" },
  { name: "updated", label: "✏️ Modifiés sur HelloAsso", color: "amber" },
  { name: "to_review", label: "⚠️ À vérifier", color: "orange" },
  { name: "already_imported", label: "✅ Déjà importés", color: "slate" },
  { name: "blocked", label: "⛔ Ignorés / bloqués", color: "red" },
];

export type MembershipCampaigns = Schemas["HelloAssoCampaigns"]["membership"];

const STATE_SUFFIXES: Record<string, string> = { Private: " (privée)", Draft: " (brouillon)" };

/** The options of the campaign select: the club's membership forms (Paramètres › Campagnes order), the active one
    marked; it is added when HelloAsso could not list it. */
export function campaignOptions(membership: MembershipCampaigns): { value: string; label: string }[] {
  const options = membership.campaigns.map((campaign) => ({
    value: campaign.slug,
    label: `${campaign.title || campaign.slug}${campaign.active ? " (campagne active)" : (STATE_SUFFIXES[campaign.state] ?? "")}`,
  }));
  const active = membership.active;
  if (active && !options.some((option) => option.value === active.slug)) {
    options.unshift({ value: active.slug, label: `${active.slug} (campagne active)` });
  }
  return options;
}

/** The rows of a bucket, the latest registrations first. */
export function rowsOf(preview: MembershipPreview, bucket: BucketName): MembershipRow[] {
  const registered = (row: MembershipRow): number => parseDate(row.order_date)?.getTime() ?? 0;
  return preview.rows.filter((row) => row.bucket === bucket).sort((a, b) => registered(b) - registered(a));
}

/** The rows matching the search of their table (accents and case ignored): name in either order, licence, tarif, birth date, reason. */
export function searchRows(rows: MembershipRow[], query: string): MembershipRow[] {
  const wanted = normKey(query);
  if (!wanted) {
    return rows;
  }
  const searched = (row: MembershipRow): string =>
    normKey(
      [personLabel(row), `${row.first_name} ${row.last_name}`, row.licence, row.tarif_name, formatDayText(row.birth_date), row.reason].join(
        " ",
      ),
    );
  return rows.filter((row) => searched(row).includes(wanted));
}

/** The buckets shown folded at first: nothing to do on them. */
export const FOLDED_BUCKETS: readonly BucketName[] = ["already_imported", "blocked"];

/** The icon of each HelloAsso status: the item state (Processed, Registered, Canceled, Unknown), replaced by the payments'
    refund state when every payment was refunded (Refunded, Refunding). */
const STATUS_ICONS: Record<string, { icon: string; label: string }> = {
  Processed: { icon: "✅", label: "Payée" },
  Registered: { icon: "📝", label: "Enregistrée sans paiement en ligne" },
  Canceled: { icon: "🚫", label: "Annulée" },
  Refunded: { icon: "↩️", label: "Remboursée" },
  Refunding: { icon: "⏳", label: "Remboursement en cours" },
};

/** French label of a HelloAsso status; an unknown value is shown as is. */
export function statusLabel(status: string): string {
  return STATUS_ICONS[status]?.label ?? status;
}

/** Icon and tooltip of a HelloAsso status (the tooltip ends with the HelloAsso value). */
export function statusIcon(status: string): { icon: string; tooltip: string } {
  const known = STATUS_ICONS[status];
  return { icon: known?.icon ?? "❔", tooltip: `${known?.label ?? "Statut inconnu"} (${status || "vide"})` };
}

/** « Remboursé le 14/10/2026 » (« Remboursement en cours depuis le … » while HelloAsso processes it). */
export function refundText(row: MembershipRow): string {
  const day = formatDayText(row.refund_date);
  return row.status === "Refunding" ? `Remboursement en cours depuis le ${day}` : `Remboursé le ${day}`;
}

export function personLabel(row: { last_name: string; first_name: string }): string {
  return `${row.last_name} ${row.first_name}`.trim();
}

export type MembershipDecision = Schemas["MembershipDecision"];
export type MembershipMember = Schemas["MembershipMember"];

/** The admin's choice on a row: whether it is checked (written), what to do with it — "import" (new, renewal,
    changed row), for a row to review "create" / "link:<member id>" ("" until chosen), "attach:<member id>" to give it
    to any member ("attach:" while none is picked) — and the comment an attach requires. Unchecking keeps the choice. */
export interface RowChoice {
  checked: boolean;
  choice: string;
  comment: string;
}
/** The choices by HelloAsso item id. */
export type Choices = Record<number, RowChoice>;

export const ATTACH = "attach:";

/** Buckets whose rows are written when checked; their checkbox starts checked. */
const CHECKABLE: readonly BucketName[] = ["new", "renewal", "updated"];

/** The row has a checkbox: every row that can be written (a row to review once a choice is made). */
export function isCheckable(row: MembershipRow): boolean {
  return CHECKABLE.includes(row.bucket) || row.bucket === "to_review";
}

/** A row to review for its identity: the admin picks a candidate, a new member or another member. */
export function needsIdentityChoice(row: MembershipRow): boolean {
  return row.bucket === "to_review" && row.changes.length === 0;
}

/** The row can be attached by hand to any member: a new or renewal row (link next to the checkbox), a row to review
    for its identity (option of its select). */
export function canAttach(row: MembershipRow): boolean {
  return row.bucket === "new" || row.bucket === "renewal" || needsIdentityChoice(row);
}

/** The member of an "attach:<member id>" choice, null while none is picked (or for another choice). */
export function attachedMemberId(choice: string): number | null {
  const id = choice.startsWith(ATTACH) ? choice.slice(ATTACH.length) : "";
  return /^\d+$/.test(id) ? Number(id) : null;
}

const MEMBERSHIP_TAGS: Record<MembershipMember["membership"], string> = {
  none: "pas encore adhérent(e) cette saison",
  manual: "reprend son adhésion manuelle",
  several_manual: "plusieurs adhésions manuelles cette saison",
  helloasso: "déjà une adhésion HelloAsso cette saison",
};

/** The member can be given a registration: not when they already have a HelloAsso membership this season, nor
    several manual ones (the one to take over would be a guess). */
export function canReceive(member: MembershipMember): boolean {
  return member.membership === "none" || member.membership === "manual";
}

/** « WEASLEY Ginny (né(e) le 11/08/2013, licence 123456) · reprend son adhésion manuelle » */
export function memberOptionLabel(member: MembershipMember): string {
  return `${candidateLabel(member)} · ${MEMBERSHIP_TAGS[member.membership]}`;
}

const SEARCH_RESULTS = 8;

/** The members matching the search of an attach (name in either order or licence, accents and case ignored), at
    most 8; none before something is typed. */
export function searchMembers(members: readonly MembershipMember[], query: string): MembershipMember[] {
  const wanted = normKey(query);
  if (!wanted) {
    return [];
  }
  const searched = (member: MembershipMember): string =>
    normKey(`${personLabel(member)} ${member.first_name} ${member.last_name} ${member.licence}`);
  return members.filter((member) => searched(member).includes(wanted)).slice(0, SEARCH_RESULTS);
}

/** The member of the preview with this id. */
export function memberOf(preview: MembershipPreview, memberId: number | null): MembershipMember | undefined {
  return preview.members.find((member) => member.user_id === memberId);
}

/** Why a checked row cannot be imported yet (an attach without member or comment, or a member chosen twice), null
    when it can. */
export function rowProblem(row: MembershipRow, preview: MembershipPreview, choices: Choices): string | null {
  const current = choices[row.item_id];
  if (!current?.checked || !current.choice.startsWith(ATTACH)) {
    return null;
  }
  const member = memberOf(preview, attachedMemberId(current.choice));
  if (!member) {
    return "Choisissez l'adhérent à rattacher.";
  }
  const chosenElsewhere = Object.entries(choices).some(
    ([itemId, other]) =>
      Number(itemId) !== row.item_id &&
      other.checked &&
      (other.choice === `${ATTACH}${member.user_id}` || other.choice === `link:${member.user_id}`),
  );
  if (chosenElsewhere) {
    return `${personLabel(member)} est déjà choisi(e) pour une autre inscription de cet import.`;
  }
  if (!current.comment.trim()) {
    return `Commentaire requis pour ${personLabel(row)}.`;
  }
  return null;
}

/** The rows the import will write: checked, with a choice, and nothing missing. */
export function selectedRows(preview: MembershipPreview, choices: Choices): MembershipRow[] {
  return preview.rows.filter((row) => {
    const current = choices[row.item_id];
    return current?.checked && current.choice && !rowProblem(row, preview, choices);
  });
}

/** The checked rows that cannot be imported yet: the import waits for them. */
export function incompleteRows(preview: MembershipPreview, choices: Choices): MembershipRow[] {
  return preview.rows.filter((row) => rowProblem(row, preview, choices) !== null);
}

/** « 🔗 WEASLEY Molly (commande 501) → WEASLEY Ginny, né(e) le 11/08/2013 · reprend son adhésion manuelle », one line
    per checked attach: the confirmation lists them. */
export function attachLines(preview: MembershipPreview, choices: Choices): string[] {
  return selectedRows(preview, choices).flatMap((row) => {
    const member = memberOf(preview, attachedMemberId(choices[row.item_id]?.choice ?? ""));
    return member
      ? [
          `🔗 ${personLabel(row)} (commande ${row.order_ref}) → ${personLabel(member)}, né(e) le ${formatDayText(member.birth_date) || "?"} · ` +
            MEMBERSHIP_TAGS[member.membership],
        ]
      : [];
  });
}

const FIELD_LABELS: Record<MembershipRow["changes"][number]["field"], string> = {
  status: "Statut",
  tarif_name: "Tarif",
  amount: "Montant",
};

/** The changes of a row: old → new, or when the CRM changed the value too, both values. */
export function changeLines(row: MembershipRow): string[] {
  return row.changes.map((change) => {
    const text = (value: string): string => (change.field === "status" ? statusLabel(value) : value);
    return row.bucket === "to_review"
      ? `${FIELD_LABELS[change.field]} : CRM ${text(change.crm)} · HelloAsso ${text(change.after)} (avant ${text(change.before)})`
      : `${FIELD_LABELS[change.field]} : ${text(change.before)} → ${text(change.after)}`;
  });
}

/** The choices the preview starts with: the new, renewal and changed rows checked, the rows to review unchecked
    (a conflict row on its single choice, the others with no choice yet). */
export function initialChoices(preview: MembershipPreview): Choices {
  const choices: Choices = {};
  for (const row of preview.rows) {
    if (CHECKABLE.includes(row.bucket)) {
      choices[row.item_id] = { checked: true, choice: "import", comment: "" };
    } else if (row.bucket === "to_review") {
      choices[row.item_id] = { checked: false, choice: needsIdentityChoice(row) ? "" : "import", comment: "" };
    }
  }
  return choices;
}

/** Body of the import: the choice of each checked row (with its comment for an attach), skip for the others, with the
    bucket the preview showed it in. */
export function decisionsOf(preview: MembershipPreview, choices: Choices): Record<number, MembershipDecision> {
  const selected = new Set(selectedRows(preview, choices).map((row) => row.item_id));
  const decisions: Record<number, MembershipDecision> = {};
  for (const row of preview.rows) {
    const current = choices[row.item_id];
    if (!current) {
      continue;
    }
    if (!selected.has(row.item_id)) {
      decisions[row.item_id] = { bucket: row.bucket, choice: "skip" };
    } else if (current.choice.startsWith(ATTACH)) {
      decisions[row.item_id] = { bucket: row.bucket, choice: current.choice, comment: current.comment.trim() };
    } else {
      decisions[row.item_id] = { bucket: row.bucket, choice: current.choice };
    }
  }
  return decisions;
}

/** Address of an imported member's record in Adhérents (its recordQuery). */
export function memberHref(member: { user_id: number; purchase_id?: number }, season: string): string {
  const query = new URLSearchParams({ id: String(member.user_id), saison: season });
  if (member.purchase_id !== undefined) {
    query.set("achat", String(member.purchase_id));
  }
  return `/bureau/adherents?${query.toString()}`;
}

/** The lists of the result screen: the members written, by what the import did. */
export const RESULT_GROUPS = [
  { key: "created", icon: "🆕", testId: "ha-created" },
  { key: "renewed", icon: "🔁", testId: "ha-renewed" },
  { key: "updated", icon: "✏️", testId: "ha-updated" },
  { key: "attached", icon: "🔗", testId: "ha-attached" },
] as const satisfies readonly { key: keyof MembershipImportResult["counts"]; icon: string; testId: string }[];

function plural(count: number, one: string, many: string): string {
  return `${count} ${count > 1 ? many : one}`;
}

/** Headline of the result screen. */
export function resultSummary(result: MembershipImportResult): string {
  const { created, renewed, updated, attached, skipped } = result.counts;
  const attachedText = attached ? `${plural(attached, "inscription rattachée", "inscriptions rattachées")}, ` : "";
  return (
    `🎉 Import terminé (saison ${result.season}) : ${plural(created, "adhérent créé", "adhérents créés")}, ` +
    `${plural(renewed, "renouvellement", "renouvellements")}, ${plural(updated, "inscription mise à jour", "inscriptions mises à jour")}, ` +
    attachedText +
    `${plural(skipped, "inscription non importée", "inscriptions non importées")}.`
  );
}

export type MembershipCandidate = Schemas["MembershipCandidate"];

/** The choices of a row to review (skipping it: unchecked): link to one of its candidates, create a new member when it
    has a birth date, or attach it to another member (picked in the search). */
export function reviewOptions(row: MembershipRow): { value: string; label: string }[] {
  return [
    ...row.candidates.map((member) => ({ value: `link:${member.user_id}`, label: `Rattacher à ${candidateLabel(member)}` })),
    ...(row.can_create ? [{ value: "create", label: "Créer un nouvel adhérent" }] : []),
    { value: ATTACH, label: "Rattacher à un autre adhérent…" },
  ];
}

function candidateLabel(member: Omit<MembershipCandidate, "user_id">): string {
  const details = [`né(e) le ${formatDayText(member.birth_date) || "?"}`, ...(member.licence ? [`licence ${member.licence}`] : [])];
  return `${personLabel(member)} (${details.join(", ")})`;
}

/** « Dernière synchro : date, par X », or the empty state before the first import. */
export function lastSyncText(last: Schemas["MembershipLastImport"] | null): string {
  if (!last) {
    return "Aucune synchronisation des adhésions HelloAsso pour l'instant.";
  }
  const date = parseDate(last.at);
  return `Dernière synchro : ${date ? formatDateTime(date) : last.at}, par ${last.author}`;
}
