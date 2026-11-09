<script setup lang="ts">
/* Outils › Clés: the club keys of the climbing wall (plans/club-keys.md). Coaches read; admins add the keys, hand
   them over, record their return, archive and restore them. A holder links to their record in Adhérents, flagged ⚠️
   without a membership of the active season; a member record links back here (?cle=<key id> opens its panel). */
import { computed, inject, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import DataTable from "../../components/DataTable.vue";
import type { DataColumn } from "../../components/dataTable";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import { AUTH_KEY } from "../../composables/auth";
import { dialogs } from "../../composables/dialogs";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { formatDayText } from "../../lib/format";
import { plural } from "../../lib/text";
import { createKeysApi } from "../../services/keys";
import { OUTILS_KEY } from "./context";
import KeyArchiveDialog from "./KeyArchiveDialog.vue";
import KeyAssignDialog from "./KeyAssignDialog.vue";
import KeyPanel from "./KeyPanel.vue";
import KeyReturnDialog from "./KeyReturnDialog.vue";
import { holderName, keyCounts, shownKeys, STATUS_LABEL, type Key } from "./keys";

const keysApi = createKeysApi(inject(CLIENT_KEY)!);
const auth = inject(AUTH_KEY)!;
const { toast } = inject(OUTILS_KEY)!;

const isAdmin = computed(() => auth.state.value.status === "signedIn" && auth.state.value.role === "admin");
const keys = ref<Key[] | null>(null);
const search = ref("");
const flaggedOnly = ref(false);
// Archived keys: hidden, behind « Afficher les archives » (as the competitions list)
const current = computed(() => (keys.value ?? []).filter((k) => k.status !== "archived"));
const archived = computed(() =>
  shownKeys(
    (keys.value ?? []).filter((k) => k.status === "archived"),
    search.value,
  ),
);
const showArchived = ref(false);
const shown = computed(() => shownKeys(current.value, search.value, flaggedOnly.value));
const archiving = ref<Key | null>(null);
const assigning = ref<Key | null>(null);
const returning = ref<Key | null>(null);
// The key whose panel is open: its id, so the panel follows the reloaded list. ?cle=<id>: the link of a member record
const route = useRoute();
const linked = Number(route.query.cle);
const selectedId = ref<number | null>(Number.isInteger(linked) && linked > 0 ? linked : null);
const selected = computed(() => keys.value?.find((k) => k.id === selectedId.value) ?? null);
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

const counted = (n: number, word: string) => `${n} ${word}${plural(n)}`;

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
  archiving.value = null;
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
            {{ counted(counts.assigned, "attribuée") }} · {{ counted(counts.available, "disponible") }} ·
            {{ counted(counts.archived, "archivée") }}
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

    <div class="flex flex-col gap-3 lg:flex-row lg:items-start">
      <div class="min-w-0 flex-1">
        <DataTable
          :selected-key="selectedId === null ? undefined : String(selectedId)"
          :on-row-click="(k: Key) => (selectedId = k.id)"
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
              <span
                v-if="!row.holder.member_this_season"
                class="cursor-help"
                title="Pas d'adhésion pour la saison active : clé à récupérer ?"
              >
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
        <button
          v-if="archived.length"
          type="button"
          data-testid="toggle-key-archives"
          :aria-expanded="showArchived"
          class="mt-2.5 cursor-pointer rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-300"
          @click="showArchived = !showArchived"
        >
          {{ showArchived ? "🙈 Masquer les archives" : `🗂 Afficher les archives (${archived.length})` }}
        </button>
        <ul v-if="showArchived" class="mt-2 flex flex-col gap-2" data-testid="archived-keys">
          <li v-for="k in archived" :key="k.id">
            <button
              type="button"
              data-testid="archived-key"
              :aria-pressed="selectedId === k.id"
              class="block w-full cursor-pointer rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-left text-xs text-slate-700 hover:border-accent"
              @click="selectedId = k.id"
            >
              <b class="text-[13px]">🔑 {{ k.code }}</b>
              · 📦 Archivée
              <template v-if="k.archive">le {{ formatDayText(k.archive.date) }} · {{ k.archive.comment }}</template>
            </button>
          </li>
        </ul>
      </div>
      <KeyPanel
        v-if="selected"
        :key="selected.id"
        class="order-first lg:order-none"
        :shown-key="selected"
        :admin="isAdmin"
        @close="selectedId = null"
        @changed="done"
        @failed="(m) => toast.show(`❌ ${m}`, 8000)"
        @assign="assigning = selected"
        @give-back="returning = selected"
        @archive="archiving = selected"
      />
    </div>

    <KeyAssignDialog
      :key-to-assign="assigning"
      :keys="keys ?? []"
      @close="assigning = null"
      @done="done"
      @failed="(m) => toast.show(`❌ ${m}`, 8000)"
    />
    <KeyArchiveDialog :key-to-archive="archiving" @close="archiving = null" @done="done" @failed="(m) => toast.show(`❌ ${m}`, 8000)" />
    <KeyReturnDialog :key-to-return="returning" @close="returning = null" @done="done" @failed="(m) => toast.show(`❌ ${m}`, 8000)" />
  </section>
</template>
