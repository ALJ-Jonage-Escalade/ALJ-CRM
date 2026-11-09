<script setup lang="ts">
/* Outils › Clés: the club keys of the climbing wall (plans/club-keys.md). Coaches read, admins add the keys. */
import { computed, inject, onMounted, ref } from "vue";
import DataTable from "../../components/DataTable.vue";
import type { DataColumn } from "../../components/dataTable";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import { AUTH_KEY } from "../../composables/auth";
import { dialogs } from "../../composables/dialogs";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createKeysApi } from "../../services/keys";
import { OUTILS_KEY } from "./context";
import { keyCounts, shownKeys, STATUS_LABEL, type Key } from "./keys";

const keysApi = createKeysApi(inject(CLIENT_KEY)!);
const auth = inject(AUTH_KEY)!;
const { toast } = inject(OUTILS_KEY)!;

const isAdmin = computed(() => auth.state.value.status === "signedIn" && auth.state.value.role === "admin");
const keys = ref<Key[] | null>(null);
const search = ref("");
const shown = computed(() => shownKeys(keys.value ?? [], search.value));
const counts = computed(() => keyCounts(keys.value ?? []));

const COLUMNS: DataColumn<Key>[] = [
  { id: "code", label: "Clé", value: (k) => k.code },
  { id: "status", label: "Statut", value: (k) => STATUS_LABEL[k.status] },
];

const plural = (n: number, word: string) => `${n} ${word}${n > 1 ? "s" : ""}`;

async function reload(): Promise<void> {
  try {
    keys.value = await keysApi.list();
  } catch (e) {
    toast.show(`❌ Clés illisibles : ${errorText(e)}`, 8000);
  }
}

async function add(): Promise<void> {
  const code = await dialogs.prompt({ title: "Ajouter une clé", label: "Numéro de la clé", confirmLabel: "Ajouter" });
  if (!code?.trim()) {
    return;
  }
  try {
    const added = await keysApi.add(code);
    toast.show(`✅ Clé « ${added.code} » ajoutée.`);
    await reload();
  } catch (e) {
    toast.show(`❌ ${errorText(e)}`, 8000);
  }
}

onMounted(reload);
defineExpose({ reload });
</script>

<template>
  <section data-testid="pane-cles">
    <UiCard class="mb-3">
      <div class="flex flex-wrap items-center justify-between gap-2.5">
        <div class="min-w-0">
          <h3 class="text-sm font-bold">🔑 Clés de la salle</h3>
          <p class="text-xs text-slate-500" data-testid="key-counts">
            {{ plural(counts.assigned, "attribuée") }} · {{ plural(counts.available, "disponible") }} ·
            {{ plural(counts.archived, "archivée") }}
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="search"
            type="search"
            data-testid="key-search"
            placeholder="Rechercher une clé…"
            aria-label="Rechercher une clé"
            class="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
          />
          <UiButton v-if="isAdmin" small data-testid="key-add" @click="add">+ Ajouter une clé</UiButton>
        </div>
      </div>
    </UiCard>

    <DataTable
      :rows="shown"
      :columns="COLUMNS"
      :row-key="(k: Key) => String(k.id)"
      :sort="{ id: 'code' }"
      label="Clés"
      :empty="keys ? 'Aucune clé.' : 'Chargement en cours…'"
    >
      <template #cell-code="{ row }">
        <b data-testid="key-code">{{ row.code }}</b>
      </template>
      <template #card="{ row }">
        <b>🔑 {{ row.code }}</b>
        <span class="ml-2 text-xs text-slate-500">{{ STATUS_LABEL[row.status] }}</span>
      </template>
    </DataTable>
  </section>
</template>
