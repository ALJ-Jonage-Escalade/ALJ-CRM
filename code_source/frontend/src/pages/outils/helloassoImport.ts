/* Import of the HelloAsso membership campaign (server: api/members/helloasso_import.py): the server sorts every
   registration of the campaign into a bucket; the preview shows one section per bucket. */
import type { BadgeColor } from "../../components/ui/palette";
import type { Schemas } from "../../lib/client";

export type MembershipPreview = Schemas["MembershipPreview"];
export type MembershipRow = Schemas["MembershipRow"];
export type BucketName = MembershipRow["bucket"];

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

export function rowsOf(preview: MembershipPreview, bucket: BucketName): MembershipRow[] {
  return preview.rows.filter((row) => row.bucket === bucket);
}

export function personLabel(row: MembershipRow): string {
  return `${row.last_name} ${row.first_name}`.trim();
}
