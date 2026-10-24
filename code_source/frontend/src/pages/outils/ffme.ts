/* Import of the licensee list exported from MyFFME (.xlsx): the file goes to the server base64 encoded; the server
   matches its rows with the members (license number, then name). The rows it could not match are shown with a list
   of members to pick from; the picked ones are sent with the file when applying. */
import type { Schemas } from "../../lib/client";

export type Licensee = Schemas["FfmeLicensee"];
export type Member = Schemas["FfmeMember"];
export type ManualMatch = Schemas["FfmeManualMatch"];

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
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export function memberLabel(m: Member): string {
  return `${m.last_name} ${m.first_name} (${m.birth_date || "—"})`;
}

/** Members in alphabetical order (last name, then first name), for the pickers. */
export function sortedMembers(members: readonly Member[]): Member[] {
  const collator = new Intl.Collator("fr", { sensitivity: "base" });
  return [...members].sort((a, b) => collator.compare(a.last_name, b.last_name) || collator.compare(a.first_name, b.first_name));
}

/** The rows linked to a member: choices[i] is the member picked for unmatched[i], null to leave the row out. */
export function manualMatches(unmatched: readonly Licensee[], choices: readonly (number | null)[]): ManualMatch[] {
  return unmatched.flatMap((row, i) => {
    const userId = choices[i];
    if (userId == null) return [];
    const { nom, prenom, licence, passeports, diplomes, document_sante } = row;
    return [{ user_id: userId, nom, prenom, licence, passeports, diplomes, document_sante }];
  });
}

export function applyConfirmation(matched: number, manual: number): string {
  return (
    `Confirmer l'enregistrement de ${matched + manual} adhérents en base de données ?\n\n` +
    `• ${matched} réconciliés automatiquement\n• ${manual} associés manuellement`
  );
}
