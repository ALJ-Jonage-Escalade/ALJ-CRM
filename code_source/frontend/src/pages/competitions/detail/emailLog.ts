/* The e-mail log of the open competition: read when it opens and after a send, not polled. The last answer is kept on
   the device for its user (one copy per competition), shown at once and while the network is down, marked stale. */
import { inject, ref, shallowRef, watch, type Ref } from "vue";
import { CLIENT_KEY } from "../../../lib/client";
import { STORE_KEY } from "../../../lib/store";
import { createCompetitionsApi } from "../../../services/competitions";
import type { EmailLog, LogView } from "./emailHistory";

export interface CompetitionEmailLog {
  view: Readonly<Ref<LogView>>;
  /** When the copy shown was read from the server; null while it is the server's latest answer (or nothing). */
  staleSince: Readonly<Ref<Date | null>>;
  refresh(): Promise<void>;
}

export function useCompetitionEmailLog(competitionId: () => number, uid: () => string | null): CompetitionEmailLog {
  const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
  const store = inject(STORE_KEY)!;
  const view = shallowRef<LogView>({ log: null, failed: false });
  const staleSince = ref<Date | null>(null);
  let generation = 0; // the answer for a competition left meanwhile is dropped

  const copyName = (id: number) => `email-log:${id}`;

  async function refresh(): Promise<void> {
    const mine = generation;
    const id = competitionId();
    try {
      const log = await competitionsApi.emailLog(id);
      if (mine !== generation) {
        return;
      }
      view.value = { log, failed: false };
      staleSince.value = null;
      const owner = uid();
      if (owner) {
        void store.save(copyName(id), owner, log, null);
      }
    } catch {
      if (mine === generation) {
        view.value = { log: view.value.log, failed: true };
      }
    }
  }

  async function open(id: number, owner: string | null): Promise<void> {
    const mine = ++generation;
    view.value = { log: null, failed: false };
    staleSince.value = null;
    if (owner) {
      await store.start(owner);
      const copy = await store.load<EmailLog>(copyName(id), owner);
      if (mine !== generation) {
        return;
      }
      if (copy) {
        view.value = { log: copy.data, failed: false };
        staleSince.value = new Date(copy.savedAt);
      }
    }
    await refresh();
  }

  watch([competitionId, uid], ([id, owner]) => void open(id, owner), { immediate: true });
  return { view, staleSince, refresh };
}
