/* Import of the licensee list exported from MyFFME (.xlsx): the file goes to the server base64 encoded; the server
   matches its rows with the members (license number, then name, checked against the birth date) and lists what the
   import changes. The rows it could not match are shown with a list of members to pick from; each pick is previewed
   again, then sent with the file when applying, with the rows the office left out. */
import type { Schemas } from "../../../lib/client";
import { normKey, plural } from "../../../lib/text";

export type Licensee = Schemas["FfmeLicensee"];
export type Member = Schemas["FfmeMember"];
export type ManualMatch = Schemas["FfmeManualMatch"];
export type RowChange = Schemas["FfmeRowChange"];

export function isXlsx(name: string): boolean {
  return name.toLowerCase().endsWith(".xlsx");
}

export function fileLabel(file: { name: string; size: number }): string {
  return `📄 Fichier sélectionné : ${file.name} (${Math.round(file.size / 1024)} Ko)`;
}

/** The file's bytes in base64 (body of /api/ffme/preview and /api/ffme/import). */
export async function readBase64(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  // By chunks: String.fromCharCode takes its bytes as arguments, which are limited in number
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

export function memberLabel(member: Member): string {
  return `${member.last_name} ${member.first_name} (${member.birth_date || "—"})`;
}

/** Members in alphabetical order (last name, then first name), for the pickers. */
export function sortedMembers(members: readonly Member[]): Member[] {
  const collator = new Intl.Collator("fr", { sensitivity: "base" });
  return [...members].sort((a, b) => collator.compare(a.last_name, b.last_name) || collator.compare(a.first_name, b.first_name));
}

const SOURCE_RANK: Record<RowChange["source"], number> = { manuel: 2, nom: 3, licence: 4 };

/** What needs a look first: matched twice, then no active registration, then by how sure the match is. */
function attentionRank(row: RowChange): number {
  if (row.duplicate) {
    return 0;
  }
  return row.no_active_registration ? 1 : SOURCE_RANK[row.source];
}

/** The changes sorted by what needs a look, then by name (accents and case ignored). */
export function sortChanges(rows: readonly RowChange[]): RowChange[] {
  const collator = new Intl.Collator("fr", { sensitivity: "base" });
  return [...rows].sort(
    (a, b) =>
      attentionRank(a) - attentionRank(b) || collator.compare(a.last_name, b.last_name) || collator.compare(a.first_name, b.first_name),
  );
}

function anyMatches(query: string, values: readonly string[]): boolean {
  const key = normKey(query);
  return values.some((value) => normKey(value).includes(key));
}

/** The search field of the preview: a change row by the member's name or licence (accents and case ignored). */
export function changeMatches(row: RowChange, query: string): boolean {
  return anyMatches(query, [row.last_name, row.first_name, row.licence]);
}

/** The search field of the preview: an unmatched row by the file's name or licence. */
export function licenseeMatches(licensee: Licensee, query: string): boolean {
  return anyMatches(query, [licensee.nom, licensee.prenom, licensee.licence]);
}

/** The members that several ticked rows point to: the import refuses them until one row is left out. */
export function blockedUserIds(rows: readonly RowChange[], excludedRows: ReadonlySet<number>): Set<number> {
  const seen = new Set<number>();
  const blocked = new Set<number>();
  for (const row of rows) {
    if (!excludedRows.has(row.row_number)) {
      (seen.has(row.user_id) ? blocked : seen).add(row.user_id);
    }
  }
  return blocked;
}

/** The rows linked to a member: choices[i] is the member picked for unmatched[i], null to leave the row out. */
export function manualMatches(unmatched: readonly Licensee[], choices: readonly (number | null)[]): ManualMatch[] {
  return unmatched.flatMap((row, i) => {
    const userId = choices[i];
    if (userId == null) {
      return [];
    }
    return [{ row_number: row.row_number, user_id: userId }];
  });
}

/** The confirmation before writing `rows` (the ticked rows that change something). */
export function applyConfirmation(rows: readonly RowChange[]): string {
  const manualCount = rows.filter((row) => row.source === "manuel").length;
  const automaticCount = rows.length - manualCount;
  return (
    `Confirmer l'enregistrement de ${rows.length} adhérent${plural(rows.length)} en base de données ?\n\n` +
    `• ${automaticCount} réconcilié${plural(automaticCount)} automatiquement\n• ${manualCount} associé${plural(manualCount)} manuellement`
  );
}
