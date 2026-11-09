/* Outils › Clés: the club keys of the climbing wall (plans/club-keys.md), what the page shows of them. */
import type { Schemas } from "../../lib/client";

export type Key = Schemas["Key"];
export type KeyStatus = Key["status"];
export type KeyHolder = NonNullable<Key["holder"]>;

export const STATUS_LABEL: Record<KeyStatus, string> = {
  available: "🟢 Disponible",
  assigned: "🔵 Attribuée",
  archived: "⚫ Archivée",
};

export const holderName = (h: { last_name: string; first_name: string }): string => `${h.last_name} ${h.first_name}`.trim();

/** The keys matching the search (code or holder, case ignored), only those of holders who did not renew when
    flaggedOnly; the table sorts them. */
export function shownKeys(keys: readonly Key[], search: string, flaggedOnly = false): Key[] {
  const needle = search.trim().toLowerCase();
  return keys.filter(
    (k) =>
      (!flaggedOnly || (k.holder && !k.holder.member_this_season)) &&
      (!needle || k.code.toLowerCase().includes(needle) || (k.holder && holderName(k.holder).toLowerCase().includes(needle))),
  );
}

export function keyCounts(keys: readonly Key[]): Record<KeyStatus, number> {
  const counts: Record<KeyStatus, number> = { assigned: 0, available: 0, archived: 0 };
  for (const k of keys) {
    counts[k.status] += 1;
  }
  return counts;
}

/** A member who may be given a key; heldCode: the key they already hold (they can't get another). */
export interface Candidate {
  user_id: number;
  name: string;
  heldCode: string | null;
}

const collator = new Intl.Collator("fr", { sensitivity: "base", numeric: true });

/** Each member of the season once, by name, with the key they hold. */
export function candidates(
  members: readonly { user_id: number; last_name: string; first_name: string }[],
  keys: readonly Key[],
): Candidate[] {
  const held = new Map(keys.flatMap((k) => (k.holder ? [[k.holder.user_id, k.code] as const] : [])));
  const unique = new Map(members.map((m) => [m.user_id, m]));
  return [...unique.values()]
    .map((m) => ({ user_id: m.user_id, name: holderName(m), heldCode: held.get(m.user_id) ?? null }))
    .sort((a, b) => collator.compare(a.name, b.name));
}
