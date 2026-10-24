/* Changes made offline on the competitions screen, sent when the network comes back (plan D2). Port of the outbox of
   the former phone page (web/competitions.html): same entries in the same store (lib/store.ts "outbox"), so what that
   page queued is sent by the app.

   Without network a coach can still switch « Participe » or « Présent » on a competitor already listed: the change
   shows at once, is kept on the device and is sent later with the participant's `updated_at` the coach saw
   (unchanged_since). The server refuses it when the participant changed meanwhile (another coach, the office, a
   payment) or the competition was archived: the change is then dropped and the coach told, never merged.
   - queue(): a second change of the same flag replaces the first; switching back to the value the server has cancels it.
   - replay(): oldest first. A refused change is dropped and listed; without network, with the server down or busy,
     what is left stays for the next try; a 401/403 stops everything (role lost: the caller wipes the store).
     Two changes of one competitor are both sent: the second uses the `updated_at` the first one produced. */
import { shallowRef, type Ref } from "vue";
import { ApiError } from "../../lib/client";
import type { OfflineStore } from "../../lib/store";
import type { Competition, Participant } from "./competitions";

export type QueuedFlag = "selectionne" | "present";
export const QUEUED_FLAGS: readonly QueuedFlag[] = ["selectionne", "present"];
const QUEUED_URL = /^\/api\/competitions\/(\d+)\/participants\/(\d+)$/;

/** An entry of the store's outbox, as the former page wrote it (flag "selectionne" only). */
export interface QueuedChange {
  key: string;
  uid: string;
  flag: QueuedFlag;
  value: boolean;
  url: string;
  unchanged_since: string;
  /** « NOM Prénom (Compétition) », for the refusal message */
  label: string;
  queuedAt: number;
}

/** Sends one change; resolves with the competition as written, rejects with an ApiError. */
export type SendChange = (
  competitionId: number,
  adherentId: number,
  body: { selectionne?: boolean; present?: boolean; unchanged_since: string },
) => Promise<Competition>;

export interface ReplayResult {
  /** Changes taken out of the outbox (sent or refused). */
  done: number;
  /** « label : reason » of each refused change. */
  refused: string[];
  /** 401/403: the account lost its role, nothing more was sent. */
  denied: boolean;
}

export interface Outbox {
  /** The changes waiting, by key. */
  changes: Readonly<Ref<ReadonlyMap<string, QueuedChange>>>;
  /** Reads the changes this user left in the store (null: signed out, nothing). */
  load(uid: string | null): Promise<void>;
  queue(uid: string, competition: Competition, participant: Participant, flag: QueuedFlag, value: boolean): Promise<void>;
  pending(competitionId: number, adherentId: number | null | undefined, flag: QueuedFlag): QueuedChange | undefined;
  /** null: nothing to send, or already sending. */
  replay(uid: string): Promise<ReplayResult | null>;
  /** Forgets the changes in memory (the store is wiped by clearAll: logout, role lost). */
  forget(): void;
}

export const outboxKey = (competitionId: number | string, adherentId: number | string, flag: string): string =>
  `${competitionId}:${adherentId}:${flag}`;

export function refusalText(e: ApiError): string {
  if (e.code === "changed") {
    return "modifié entre-temps sur un autre appareil";
  }
  if (e.code === "already_paid") {
    return "a payé entre-temps : passez par l'annulation";
  }
  if (e.code === "competition_closed") {
    return "compétition archivée";
  }
  if (e.status === 404) {
    return "n'est plus inscrit à cette compétition";
  }
  return e.message || `HTTP ${e.status}`;
}

/** Network down, server down or busy: kept for the next try. */
const retryLater = (e: ApiError) => e.status === 0 || e.status >= 500 || e.status === 429;

function isValid(entry: QueuedChange, uid: string): boolean {
  // Only the route and flags the queue allows, for this account (the store is local data)
  return entry.uid === uid && QUEUED_URL.test(String(entry.url)) && QUEUED_FLAGS.includes(entry.flag) && typeof entry.value === "boolean";
}

const s = (n: number) => (n > 1 ? "s" : "");

/** Confirmation asked before signing out with changes not sent yet (they are lost with the store). */
export function logoutWarning(n: number): string {
  return `${n} modification${s(n)} faite${s(n)} hors ligne pas encore envoyée${s(n)} ser${n > 1 ? "ont" : "a"} perdue${s(n)}. Se déconnecter ?`;
}

export function pendingLine(n: number): string {
  return n ? ` · ⏳ ${n} modification${s(n)} à envoyer` : "";
}

/** The toast after a replay. */
export function replayMessage(r: ReplayResult): string {
  const n = r.refused.length;
  if (!n) {
    return "☁️ Modifications faites hors ligne envoyées.";
  }
  return `⚠️ ${n} modification${s(n)} faite${s(n)} hors ligne refusée${s(n)} : ${r.refused.join(" ; ")}`;
}

export function createOutbox(store: OfflineStore, send: SendChange, now: () => number = Date.now): Outbox {
  const changes = shallowRef<ReadonlyMap<string, QueuedChange>>(new Map());
  let replaying = false;
  let generation = 0; // forget() or another load: a replay or load still running is dropped

  function set(update: (m: Map<string, QueuedChange>) => void): void {
    const next = new Map(changes.value);
    update(next);
    changes.value = next;
  }

  async function load(uid: string | null): Promise<void> {
    const mine = ++generation;
    changes.value = new Map();
    if (!uid) {
      return;
    }
    const entries = await store.queued(uid);
    // Entries are checked when sent: one written by another version is refused then, not lost silently
    if (mine === generation) {
      changes.value = new Map(entries.map((e) => [e.key, e as unknown as QueuedChange]));
    }
  }

  async function queue(uid: string, competition: Competition, participant: Participant, flag: QueuedFlag, value: boolean): Promise<void> {
    const adherentId = Number(participant.adherent_id);
    const key = outboxKey(competition.id, adherentId, flag);
    if (value === !!participant[flag]) {
      set((m) => m.delete(key));
      await store.unqueue(key);
      return;
    }
    const change: QueuedChange = {
      key,
      uid,
      flag,
      value,
      url: `/api/competitions/${competition.id}/participants/${adherentId}`,
      unchanged_since: String(participant.updated_at ?? ""),
      label: `${participant.nom ?? ""} ${participant.prenom ?? ""} (${competition.nom || "compétition"})`.trim(),
      queuedAt: changes.value.get(key)?.queuedAt ?? now(),
    };
    set((m) => m.set(key, change));
    await store.queue(uid, { ...change });
  }

  function pending(competitionId: number, adherentId: number | null | undefined, flag: QueuedFlag): QueuedChange | undefined {
    return adherentId == null ? undefined : changes.value.get(outboxKey(competitionId, adherentId, flag));
  }

  /* Out of the outbox, unless changed again meanwhile: the newer change stays. */
  async function drop(entry: QueuedChange): Promise<void> {
    if (changes.value.get(entry.key) !== entry) {
      return;
    }
    set((m) => m.delete(entry.key));
    await store.unqueue(entry.key);
  }

  async function replay(uid: string): Promise<ReplayResult | null> {
    if (replaying || !changes.value.size) {
      return null;
    }
    replaying = true;
    const mine = generation;
    const result: ReplayResult = { done: 0, refused: [], denied: false };
    // Competitor url -> the updated_at our own sent change replaced, and the one it produced
    const written = new Map<string, { from: string; to: string }>();
    try {
      for (const entry of [...changes.value.values()].sort((a, b) => a.queuedAt - b.queuedAt)) {
        if (mine !== generation) {
          return null;
        }
        if (!isValid(entry, uid)) {
          result.refused.push(`${entry.label || "?"} : modification non valide, non envoyée`);
        } else {
          const [, competitionId, adherentId] = QUEUED_URL.exec(entry.url)!.map(Number);
          const ours = written.get(entry.url);
          const unchangedSince = ours && ours.from === entry.unchanged_since ? ours.to : String(entry.unchanged_since ?? "");
          try {
            const competition = await send(competitionId!, adherentId!, { [entry.flag]: entry.value, unchanged_since: unchangedSince });
            const after = competition.participants?.find((p) => p.adherent_id === adherentId)?.updated_at;
            if (after != null) {
              written.set(entry.url, { from: entry.unchanged_since, to: String(after) });
            }
          } catch (e) {
            const error = e instanceof ApiError ? e : new ApiError(0, null, "Erreur inattendue.");
            if (retryLater(error)) {
              break;
            }
            if (error.status === 401 || error.status === 403) {
              result.denied = true;
              return result;
            }
            result.refused.push(`${entry.label} : ${refusalText(error)}`);
          }
        }
        if (mine !== generation) {
          return null;
        }
        await drop(entry);
        result.done++;
      }
    } finally {
      replaying = false;
    }
    return result.done ? result : null;
  }

  function forget(): void {
    generation++;
    changes.value = new Map();
  }

  return { changes, load, queue, pending, replay, forget };
}
