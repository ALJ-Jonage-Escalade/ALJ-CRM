<script setup lang="ts">
/* A list of sends from the e-mail log, newest first: kind, author, template or subject, recipients, and the
   competitions when their names are given (Historique des envois); each send opens to its recipients, with the
   address used and its status. Used by the competition page and Communications › Historique des envois. */
import { failedCount, isInternal, KIND_LABELS, momentOf, type EmailLogEntry } from "../lib/emailLog";
import { plural } from "../lib/text";

const props = defineProps<{
  entries: readonly EmailLogEntry[];
  /** Names of the competitions, by id: shown on each send about them (none on the competition page itself). */
  competitionNames?: Readonly<Record<number, string>>;
}>();
const author = (entry: EmailLogEntry) => (entry.author === "system" ? "envoi automatique" : entry.author);
const competitionsOf = (entry: EmailLogEntry): string[] =>
  props.competitionNames ? (entry.competition_ids ?? []).flatMap((id) => props.competitionNames?.[id] ?? []) : [];
</script>

<template>
  <p v-if="!entries.length" class="text-[13px] text-slate-500" data-testid="history-empty">Aucun e-mail enregistré.</p>
  <ul v-else class="flex flex-col gap-2" data-testid="history">
    <li v-for="(entry, i) in entries" :key="`${entry.at}-${i}`" data-testid="history-entry">
      <details class="rounded-lg border border-slate-200 text-[13px]" :class="isInternal(entry.kind) ? 'bg-slate-50' : 'bg-white'">
        <summary class="cursor-pointer px-3 py-2 select-none">
          <b>{{ momentOf(entry.at) }}</b>
          · {{ KIND_LABELS[entry.kind] }}
          <span v-if="competitionsOf(entry).length" data-testid="history-competitions">· 🏆 {{ competitionsOf(entry).join(", ") }}</span>
          <span class="block text-xs text-slate-500">
            {{ author(entry) }} · {{ entry.template || entry.subject || "sans objet" }} · {{ entry.recipients?.length ?? 0 }} destinataire{{
              plural(entry.recipients?.length ?? 0)
            }}
            <b v-if="failedCount(entry)" class="text-red-600" data-testid="history-failures">· {{ failedCount(entry) }} en échec</b>
          </span>
        </summary>
        <p v-if="entry.template && entry.subject" class="px-3 text-xs text-slate-500">Objet : {{ entry.subject }}</p>
        <ul class="divide-y divide-slate-100 px-3 pb-2">
          <li
            v-for="(r, j) in entry.recipients ?? []"
            :key="j"
            class="flex justify-between gap-2 py-1 text-xs"
            data-testid="history-recipient"
          >
            <span class="min-w-0 break-all">{{ r.name ? `${r.name} — ` : "" }}{{ r.email }}</span>
            <span v-if="r.status === 'sent'" class="shrink-0 font-semibold text-green-700">✓ envoyé</span>
            <span v-else class="shrink-0 font-semibold text-red-600" :title="r.error ?? ''">✗ échec</span>
          </li>
        </ul>
      </details>
    </li>
  </ul>
</template>
