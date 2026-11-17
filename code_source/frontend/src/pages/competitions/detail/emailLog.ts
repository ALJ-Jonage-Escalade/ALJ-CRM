/* The e-mail log of the open competition: read when it opens and after a send, not polled. */
import { inject, shallowRef, watch, type Ref } from "vue";
import { CLIENT_KEY } from "../../../lib/client";
import { createCompetitionsApi } from "../../../services/competitions";
import type { LogView } from "./emailHistory";

export interface CompetitionEmailLog {
  view: Readonly<Ref<LogView>>;
  refresh(): Promise<void>;
}

export function useCompetitionEmailLog(competitionId: () => number): CompetitionEmailLog {
  const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
  const view = shallowRef<LogView>({ log: null, failed: false });
  let generation = 0; // the answer for a competition left meanwhile is dropped

  async function refresh(): Promise<void> {
    const mine = generation;
    try {
      const log = await competitionsApi.emailLog(competitionId());
      if (mine === generation) {
        view.value = { log, failed: false };
      }
    } catch {
      if (mine === generation) {
        view.value = { log: view.value.log, failed: true };
      }
    }
  }

  async function open(): Promise<void> {
    generation++;
    view.value = { log: null, failed: false };
    await refresh();
  }

  watch(competitionId, () => void open(), { immediate: true });
  return { view, refresh };
}
