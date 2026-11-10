/* Changes of the competitions screen, provided by the page to its panes: every change goes through the API (the server
   checks roles, validation and concurrent changes). Without network only « Participe » and « Présent » can change (the
   outbox, outbox.ts); every other change is refused at once. The competition a write answers is shown at once, then
   the data is reloaded: others' changes come with it. */
import { ref, type InjectionKey, type Ref } from "vue";
import { ApiError, errorText } from "../../lib/client";
import type { Competition } from "./competitions";

export const OFFLINE_MESSAGE =
  "📴 Hors ligne : seules les cases « Participe » et « Présent » d'un compétiteur inscrit peuvent être modifiées.";
export const WRITE_NOT_SENT_MESSAGE = "📴 Réseau indisponible : modification non enregistrée.";

export interface RunOptions<T> {
  /** Toast after success. */
  done?: string | ((answer: T) => string);
  /** A refusal the caller handles itself (true: no toast). */
  refused?: (error: ApiError) => boolean;
  /** The competition the answer carries, shown at once (the reload then brings the others' changes). */
  competition?: (answer: T) => Competition;
}

/** RunOptions.competition of the writes that answer the competition itself. */
export const competitionItself = (competition: Competition): Competition => competition;

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
      if (options.competition) {
        deps.apply(options.competition(answer));
      }
      deps.reload();
      const done = typeof options.done === "function" ? options.done(answer) : options.done;
      if (done) {
        deps.toast(done);
      }
      return answer;
    } catch (e) {
      if (!(e instanceof ApiError)) {
        console.error("Modification de compétition :", e); // a bug, not a refusal: kept for the console
        deps.toast(`❌ ${errorText(e)}`, 9000);
        return undefined;
      }
      if (!options.refused?.(e)) {
        deps.toast(e.status === 0 && e.code === "network" ? WRITE_NOT_SENT_MESSAGE : `❌ ${e.message}`, 9000);
      }
      return undefined;
    } finally {
      busy.value = --running > 0;
    }
  }

  return { busy, online: () => deps.online(), dropped: (id) => deps.dropped(id), run, toast: (message, ms) => deps.toast(message, ms) };
}

export const WRITER_KEY: InjectionKey<Writer> = Symbol("competition-writer");
