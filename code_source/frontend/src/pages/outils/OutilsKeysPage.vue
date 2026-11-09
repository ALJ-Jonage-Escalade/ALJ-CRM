<script setup lang="ts">
/* Outils › Clés: the club keys of the climbing wall (plans/club-keys.md). Coaches read; admins add the keys, hand
   them over and record their return. A holder links to their record in Adhérents, flagged ⚠️ without a membership of
   the active season. */
import { computed, inject, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import DataTable from "../../components/DataTable.vue";
import type { DataColumn } from "../../components/dataTable";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import { AUTH_KEY } from "../../composables/auth";
import { dialogs } from "../../composables/dialogs";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { formatDayText } from "../../lib/format";
import { createKeysApi } from "../../services/keys";
import { OUTILS_KEY } from "./context";
import KeyAssignDialog from "./KeyAssignDialog.vue";
import KeyReturnDialog from "./KeyReturnDialog.vue";
import { holderName, keyCounts, shownKeys, STATUS_LABEL, type Key } from "./keys";

const keysApi = createKeysApi(inject(CLIENT_KEY)!);
const auth = inject(AUTH_KEY)!;
const { toast } = inject(OUTILS_KEY)!;

const isAdmin = computed(() => auth.state.value.status === "signedIn" && auth.state.value.role === "admin");
const keys = ref<Key[] | null>(null);
const search = ref("");
const flaggedOnly = ref(false);
const shown = computed(() => shownKeys(keys.value ?? [], search.value, flaggedOnly.value));
const assigning = ref<Key | null>(null);
const returning = ref<Key | null>(null);
const counts = computed(() => keyCounts(keys.value ?? []));

const COLUMNS: DataColumn<Key>[] = [
  { id: "code", label: "Clé", value: (k) => k.code },
  { id: "status", label: "Statut", value: (k) => STATUS_LABEL[k.status] },
  { id: "holder", label: "Détenteur", value: (k) => (k.holder ? holderName(k.holder) : "") },
  { id: "given_on", label: "Remise le", value: (k) => k.holder?.given_on ?? "", descFirst: true },
  { id: "comment", label: "Commentaire", value: (k) => k.holder?.comment ?? "", fixed: true },
  { id: "actions", label: "", value: () => "", fixed: true, class: "text-right" },
];
const holderLink = (k: Key) =>
  k.holder ? `/bureau/adherents?${new URLSearchParams({ id: String(k.holder.user_id), saison: k.holder.season })}` : "";

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

async function done(message: string): Promise<void> {
  assigning.value = null;
  returning.value = null;
  toast.show(message);
  await reload();
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
            placeholder="Clé ou détenteur…"
            aria-label="Rechercher une clé ou un détenteur"
            class="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
          />
          <label class="inline-flex items-center gap-1.5 text-xs text-slate-600">
            <input v-model="flaggedOnly" type="checkbox" data-testid="key-only-flagged" />
            ⚠️ Détenteurs non réinscrits uniquement
          </label>
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
      :hidden="isAdmin ? [] : ['actions']"
      :empty="keys ? 'Aucune clé.' : 'Chargement en cours…'"
    >
      <template #cell-code="{ row }">
        <b data-testid="key-code">{{ row.code }}</b>
      </template>
      <template #cell-holder="{ row }">
        <span v-if="row.holder" data-testid="key-holder">
          <RouterLink
            :to="holderLink(row)"
            class="text-slate-800 no-underline hover:text-accent hover:underline"
            title="Ouvrir la fiche adhérent"
          >
            {{ holderName(row.holder) }}
          </RouterLink>
          <span v-if="!row.holder.member_this_season" class="cursor-help" title="Pas d'adhésion pour la saison active : clé à récupérer ?">
            ⚠️
          </span>
        </span>
        <span v-else class="text-slate-400">—</span>
      </template>
      <template #cell-given_on="{ row }">
        <span v-if="row.holder" data-testid="key-given-on">{{ formatDayText(row.holder.given_on) }}</span>
        <span v-else class="text-slate-400">—</span>
      </template>
      <template #cell-actions="{ row }">
        <span data-testid="key-actions">
          <UiButton v-if="row.status === 'available'" small :data-testid="`key-assign-${row.id}`" @click="assigning = row">
            Remettre
          </UiButton>
          <UiButton
            v-else-if="row.status === 'assigned'"
            small
            variant="muted"
            :data-testid="`key-return-${row.id}`"
            @click="returning = row"
          >
            Retour
          </UiButton>
        </span>
      </template>
      <template #card="{ row }">
        <b>🔑 {{ row.code }}</b>
        <span class="ml-2 text-xs text-slate-500">{{ STATUS_LABEL[row.status] }}</span>
        <div v-if="row.holder" class="text-xs">
          <RouterLink :to="holderLink(row)">{{ holderName(row.holder) }}</RouterLink>
          <template v-if="!row.holder.member_this_season">⚠️</template>
          · depuis le {{ formatDayText(row.holder.given_on) }}
        </div>
      </template>
    </DataTable>

    <KeyAssignDialog
      :key-to-assign="assigning"
      :keys="keys ?? []"
      @close="assigning = null"
      @done="done"
      @failed="(m) => toast.show(`❌ ${m}`, 8000)"
    />
    <KeyReturnDialog :key-to-return="returning" @close="returning = null" @done="done" @failed="(m) => toast.show(`❌ ${m}`, 8000)" />
  </section>
</template>
