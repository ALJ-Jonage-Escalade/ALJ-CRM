/* Import of the HelloAsso membership campaign (server: api/members/helloasso_import.py): the server sorts every
   registration of the campaign into a bucket; the preview shows one section per bucket. */
import type { BadgeColor } from "../../components/ui/palette";
import type { Schemas } from "../../lib/client";
import { formatDateTime, formatDayText, parseDate } from "../../lib/format";

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

/** The rows of a bucket, the latest registrations first. */
export function rowsOf(preview: MembershipPreview, bucket: BucketName): MembershipRow[] {
  const registered = (row: MembershipRow): number => parseDate(row.order_date)?.getTime() ?? 0;
  return preview.rows.filter((row) => row.bucket === bucket).sort((a, b) => registered(b) - registered(a));
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
/** The admin's choice for each row, by HelloAsso item id: "import" / "skip", or for a row to review "create" /
    "skip" / "link:<member id>". */
export type Choices = Record<number, string>;

/** Buckets whose rows are written when checked; their checkbox starts checked. */
const CHECKABLE: readonly BucketName[] = ["new", "renewal", "updated"];

/** The row has a checkbox: a new, renewal or changed row, or a row to review whose values changed on both sides
    (unchecked at first: the HelloAsso values replace the CRM ones only when checked). */
export function isCheckable(row: MembershipRow): boolean {
  return CHECKABLE.includes(row.bucket) || (row.bucket === "to_review" && row.changes.length > 0);
}

/** A row to review for its identity: the admin picks a candidate, a new member or skip. */
export function needsIdentityChoice(row: MembershipRow): boolean {
  return row.bucket === "to_review" && row.changes.length === 0;
}

const FIELD_LABELS: Record<MembershipRow["changes"][number]["field"], string> = {
  status: "Statut",
  tarif_name: "Tarif",
  amount: "Montant",
};

/** The changes of a row: old → new, or when the CRM changed the value too, both values. */
export function changeLines(row: MembershipRow): string[] {
  return row.changes.map((change) =>
    row.bucket === "to_review"
      ? `${FIELD_LABELS[change.field]} : CRM ${change.crm} · HelloAsso ${change.after} (avant ${change.before})`
      : `${FIELD_LABELS[change.field]} : ${change.before} → ${change.after}`,
  );
}

/** The choices the preview starts with: the new, renewal and changed rows checked, the rows to review skipped. */
export function initialChoices(preview: MembershipPreview): Choices {
  const choices: Choices = {};
  for (const row of preview.rows) {
    if (CHECKABLE.includes(row.bucket)) {
      choices[row.item_id] = "import";
    } else if (row.bucket === "to_review") {
      choices[row.item_id] = "skip";
    }
  }
  return choices;
}

/** Body of the import: the choice of each row, with the bucket the preview showed it in. */
export function decisionsOf(preview: MembershipPreview, choices: Choices): Record<number, MembershipDecision> {
  const decisions: Record<number, MembershipDecision> = {};
  for (const row of preview.rows) {
    const choice = choices[row.item_id];
    if (choice) {
      decisions[row.item_id] = { bucket: row.bucket, choice };
    }
  }
  return decisions;
}

/** Address of an imported member's record in Adhérents (its recordQuery). */
export function memberHref(member: { user_id: number; purchase_id: number }, season: string): string {
  const query = new URLSearchParams({ id: String(member.user_id), saison: season, achat: String(member.purchase_id) });
  return `/bureau/adherents?${query.toString()}`;
}

/** The lists of the result screen: the members written, by what the import did. */
export const RESULT_GROUPS = [
  { key: "created", icon: "🆕", testId: "ha-created" },
  { key: "renewed", icon: "🔁", testId: "ha-renewed" },
  { key: "updated", icon: "✏️", testId: "ha-updated" },
] as const satisfies readonly { key: keyof MembershipImportResult["counts"]; icon: string; testId: string }[];

function plural(count: number, one: string, many: string): string {
  return `${count} ${count > 1 ? many : one}`;
}

/** Headline of the result screen. */
export function resultSummary(result: MembershipImportResult): string {
  const { created, renewed, updated, skipped } = result.counts;
  return (
    `🎉 Import terminé (saison ${result.season}) : ${plural(created, "adhérent créé", "adhérents créés")}, ` +
    `${plural(renewed, "renouvellement", "renouvellements")}, ${plural(updated, "inscription mise à jour", "inscriptions mises à jour")}, ` +
    `${plural(skipped, "inscription non importée", "inscriptions non importées")}.`
  );
}

export type MembershipCandidate = Schemas["MembershipCandidate"];

/** The choices of a row to review: skip (the default), link to one of its candidates, or create a new member when it
    has a birth date. */
export function reviewOptions(row: MembershipRow): { value: string; label: string }[] {
  return [
    { value: "skip", label: "— Ignorer cette inscription —" },
    ...row.candidates.map((member) => ({ value: `link:${member.user_id}`, label: `Rattacher à ${candidateLabel(member)}` })),
    ...(row.can_create ? [{ value: "create", label: "Créer un nouvel adhérent" }] : []),
  ];
}

function candidateLabel(member: MembershipCandidate): string {
  const details = [`né(e) le ${member.birth_date || "?"}`, ...(member.licence ? [`licence ${member.licence}`] : [])];
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
