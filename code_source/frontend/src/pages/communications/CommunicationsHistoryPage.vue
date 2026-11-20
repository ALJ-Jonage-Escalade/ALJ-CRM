<script setup lang="ts">
/* Communications › Historique des envois (admins): the latest e-mails the app sent (server: GET /api/admin/email-log),
   filtered on the device by kind and by one search text (recipient, author, subject, template, competition).
   Online only: offline or on an error the page says the history is unavailable, never that nothing was sent. */
import { computed, inject, onMounted, reactive, ref } from "vue";
import EmailHistory from "../../components/EmailHistory.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import { CLIENT_KEY, errorText, type Schemas } from "../../lib/client";
import { filterEntries, KIND_LABELS, type EmailLogFilter } from "../../lib/emailLog";
import { plural } from "../../lib/text";
import { createCommunicationsApi } from "../../services/communications";

const communicationsApi = createCommunicationsApi(inject(CLIENT_KEY)!);

const log = ref<Schemas["RecentEmailLog"] | null>(null);
const loadError = ref("");
const loading = ref(false);
const filter = reactive<EmailLogFilter>({ kind: "", search: "" });
const kinds = Object.entries(KIND_LABELS);

const shown = computed(() => (log.value ? filterEntries(log.value.entries, filter, log.value.competition_names) : []));

async function load(): Promise<void> {
  loading.value = true;
  try {
    log.value = await communicationsApi.emailLog();
    loadError.value = "";
  } catch (e) {
    loadError.value = errorText(e);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <UiCard>
    <h2 class="mb-2.5 text-[15px] font-bold">📨 Historique des envois</h2>
    <div class="mb-3 flex flex-wrap items-end gap-2">
      <div class="min-w-48">
        <label for="history-kind" class="mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase">Type d'envoi</label>
        <select
          id="history-kind"
          v-model="filter.kind"
          data-testid="history-kind"
          class="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]"
        >
          <option value="">Tous</option>
          <option v-for="[kind, label] in kinds" :key="kind" :value="kind">{{ label }}</option>
        </select>
      </div>
      <div class="min-w-48 flex-1">
        <label for="history-search" class="mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase">Rechercher</label>
        <input
          id="history-search"
          v-model="filter.search"
          type="search"
          data-testid="history-search"
          placeholder="Destinataire, adresse, auteur, objet, compétition…"
          class="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-[13px]"
        />
      </div>
    </div>

    <div v-if="loadError" class="flex flex-wrap items-center gap-2" data-testid="history-error">
      <p class="text-[13px] text-red-600">❌ Historique indisponible : {{ loadError }}</p>
      <UiButton variant="muted" small :busy="loading && 'Chargement…'" data-testid="history-retry" @click="load">🔄 Réessayer</UiButton>
    </div>
    <p v-else-if="!log" class="text-[13px] text-slate-500">Chargement…</p>
    <template v-else>
      <p v-if="log.truncated" class="mb-2 text-xs text-slate-500" data-testid="history-truncated">
        Seuls les {{ log.entries.length }} derniers envois sont affichés.
      </p>
      <p v-if="log.entries.length && !shown.length" class="text-[13px] text-slate-500" data-testid="history-no-match">
        Aucun envoi ne correspond à ces filtres.
      </p>
      <template v-else>
        <p v-if="shown.length" class="mb-2 text-xs text-slate-500">{{ shown.length }} envoi{{ plural(shown.length) }}</p>
        <EmailHistory :entries="shown" :competition-names="log.competition_names" />
      </template>
    </template>
  </UiCard>
</template>
