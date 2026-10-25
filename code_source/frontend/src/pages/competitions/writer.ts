/* Changes of the competitions screen, provided by the page to its panes: every change goes through the API (the server
   checks roles, validation and concurrent changes). Without network only « Participe » and « Présent » can change (the
   outbox, outbox.ts); every other change is refused at once. The competition a write answers is shown at once, then
   the data is reloaded: others' changes come with it. */
import { ref, type InjectionKey, type Ref } from "vue";
import { ApiError } from "../../lib/client";
import type { Competition } from "./competitions";

export const OFFLINE_MESSAGE =
  "📴 Hors ligne : seules les cases « Participe » et « Présent » d'un compétiteur inscrit peuvent être modifiées.";
export const NETWORK_MESSAGE = "📴 Réseau indisponible : modification non enregistrée.";

export interface RunOptions<T> {
  /** Toast after success. */
  done?: string | ((answer: T) => string);
  /** A refusal the caller handles itself (true: no toast). */
  refused?: (error: ApiError) => boolean;
}

export interface Writer {
  /** A change in progress (buttons wait). */
  busy: Readonly<Ref<boolean>>;
  /** The API can be reached: false offline, where only the outbox takes changes. */
  online(): boolean;
  /** Takes a deleted competition off the list at once. */
  dropped(competitionId: number): void;
  /** The answer, or undefined when refused (already told). */
  run<T>(call: () => Promise<T>, options?: RunOptions<T>): Promise<T | undefined>;
  toast(message: string, ms?: number): void;
}

export interface WriterDeps {
  online(): boolean;
  /** Shows the competition a write answered. */
  apply(competition: Competition): void;
  dropped(competitionId: number): void;
  /** Reloads the data after a change. */
  reload(): void;
  toast(message: string, ms?: number): void;
}

/** The competition carried by a write's answer: the competition itself, or { competition } (load-group). */
export function answeredCompetition(answer: unknown): Competition | null {
  const a = answer as { id?: unknown; participants?: unknown; competition?: unknown } | null;
  if (a && typeof a.id === "number" && Array.isArray(a.participants)) {
    return a as Competition;
  }
  if (a && a.competition) {
    return answeredCompetition(a.competition);
  }
  return null;
}

export function createWriter(deps: WriterDeps): Writer {
  const busy = ref(false);
  let running = 0;

  async function run<T>(call: () => Promise<T>, options: RunOptions<T> = {}): Promise<T | undefined> {
    if (!deps.online()) {
      deps.toast(OFFLINE_MESSAGE, 6000);
      return undefined;
    }
    running++;
    busy.value = true;
    try {
      const answer = await call();
      const competition = answeredCompetition(answer);
      if (competition) {
        deps.apply(competition);
      }
      deps.reload();
      const done = typeof options.done === "function" ? options.done(answer) : options.done;
      if (done) {
        deps.toast(done);
      }
      return answer;
    } catch (e) {
      const error = e instanceof ApiError ? e : new ApiError(0, null, "Erreur inattendue.");
      if (!options.refused?.(error)) {
        deps.toast(error.status === 0 && error.code === "network" ? NETWORK_MESSAGE : `❌ ${error.message}`, 9000);
      }
      return undefined;
    } finally {
      busy.value = --running > 0;
    }
  }

  return { busy, online: () => deps.online(), dropped: (id) => deps.dropped(id), run, toast: (message, ms) => deps.toast(message, ms) };
}

export const WRITER_KEY: InjectionKey<Writer> = Symbol("competition-writer");
