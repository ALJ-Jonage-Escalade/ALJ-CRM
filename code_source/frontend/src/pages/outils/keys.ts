/* Outils › Clés: the club keys of the climbing wall (plans/club-keys.md), what the page shows of them. */
import type { Schemas } from "../../lib/client";

export type Key = Schemas["Key"];
export type KeyStatus = Key["status"];

export const STATUS_LABEL: Record<KeyStatus, string> = {
  available: "🟢 Disponible",
  assigned: "🔵 Attribuée",
  archived: "⚫ Archivée",
};

/** The keys matching the search (on the code, case ignored); the table sorts them. */
export function shownKeys(keys: readonly Key[], search: string): Key[] {
  const needle = search.trim().toLowerCase();
  return keys.filter((k) => !needle || k.code.toLowerCase().includes(needle));
}

export function keyCounts(keys: readonly Key[]): Record<KeyStatus, number> {
  const counts: Record<KeyStatus, number> = { assigned: 0, available: 0, archived: 0 };
  for (const k of keys) {
    counts[k.status] += 1;
  }
  return counts;
}
