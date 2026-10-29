<script setup lang="ts">
/* Compétitions › Compétitions, the index route of the competitions page: the list (cards, table or calendar, archives
   apart) and the open competition's participants (?id=…). Any role: read-only accounts too, without contacts nor changes. */
import { computed, inject, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import { dialogs } from "../../composables/dialogs";
import { CLIENT_KEY, type Schemas } from "../../lib/client";
import { plural } from "../../lib/text";
import { createCompetitionsApi } from "../../services/competitions";
import CompetitionDetail from "./detail/CompetitionDetail.vue";
import CompetitionForm from "./CompetitionForm.vue";
import { participantRows, period, todayIso, type Competition } from "./competitions";
import { COMPETITIONS_KEY } from "./context";
import CompetitionCalendar from "./list/CompetitionCalendar.vue";
import CompetitionCards from "./list/CompetitionCards.vue";
import CompetitionFilters from "./list/CompetitionFilters.vue";
import CompetitionStats from "./list/CompetitionStats.vue";
import CompetitionTable from "./list/CompetitionTable.vue";
import { useCompetitionFilters, type ViewMode } from "./list/filters";
import ViewSwitcher from "./list/ViewSwitcher.vue";
import { WRITER_KEY } from "./writer";

const { all, competitions, competitors, members, coaches, canWrite, staff, contactsShown, online, outbox, uid } = inject(COMPETITIONS_KEY)!;
const writer = inject(WRITER_KEY)!;
const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
const route = useRoute();
const router = useRouter();

const today = todayIso();
const {
  search,
  when,
  selectedSeason,
  seasons,
  seasonCompetitions,
  current,
  archived: archivedCompetitions,
  calendar: calendarCompetitions,
  past: pastCompetitions,
  filtered,
} = useCompetitionFilters(all, today);
const viewMode = ref<ViewMode>("cards");

const selectedId = computed(() => (typeof route.query.id === "string" ? route.query.id : ""));
// The detail is shown next to the cards: a competition opened from the table or the calendar goes back to them (their
// open event covers the competition already selected, which leaves the URL unchanged)
watch(selectedId, (id) => {
  if (id) {
    viewMode.value = "cards";
  }
});
const selected = computed(() => all.value.find((c) => String(c.id) === selectedId.value));
const rows = computed(() =>
  selected.value
    ? participantRows(
        selected.value,
        members.data.value ?? [],
        contactsShown.value ? (competitors.data.value ?? []) : [],
        (id, flag) => outbox.pending(selected.value!.id, id, flag)?.value,
      )
    : [],
);

const creating = ref(false);
const editingCompetition = ref<Competition | null>(null);
const editDialogOpen = computed({
  get: () => Boolean(editingCompetition.value),
  set: (val: boolean) => {
    if (!val) {
      editingCompetition.value = null;
    }
  },
});

function openFromCalendar(c: Competition): void {
  viewMode.value = "cards";
  void router.push({ query: { id: String(c.id) } });
}

function editFromTable(c: Competition): void {
  editingCompetition.value = c;
}

async function saveFromTable(body: Schemas["CompetitionCreate"]): Promise<void> {
  if (!editingCompetition.value) {
    return;
  }
  const id = editingCompetition.value.id;
  const ok = await writer.run(() => competitionsApi.update(id, body), {
    done: "✅ Compétition mise à jour.",
  });
  if (ok) {
    editingCompetition.value = null;
  }
}

async function removeFromTable(c: Competition): Promise<void> {
  const ok = await dialogs.confirm({
    title: "Supprimer la compétition",
    message: `Supprimer définitivement « ${c.nom} » et sa liste de compétiteurs ?`,
    confirmLabel: "Supprimer",
    variant: "danger",
  });
  if (!ok) {
    return;
  }
  await writer.run(() => competitionsApi.remove(c.id), {
    done: "🗑 Compétition supprimée.",
  });
}

async function create(body: Schemas["CompetitionCreate"]): Promise<void> {
  const created = await writer.run(() => competitionsApi.create(body), { done: "✅ Compétition créée." });
  if (!created) {
    return;
  }
  creating.value = false;
  await router.push({ query: { id: String(created.id) } });
}

async function archivePastCompetitions(): Promise<void> {
  const pastCompetitionsList = pastCompetitions.value;
  const nbPastCompetitions = pastCompetitionsList.length;
  if (!nbPastCompetitions) {
    return;
  }
  if (
    !(await dialogs.confirm({
      title: "Archiver les compétitions passées",
      message: `Archiver ${nbPastCompetitions} compétition${plural(nbPastCompetitions)} passée${plural(nbPastCompetitions)} ?\n\n${pastCompetitionsList.map((competition) => `• ${competition.nom} (${period(competition)})`).join("\n")}\n\nElles resteront consultables dans les archives et comptées dans le bilan.`,
      confirmLabel: "Archiver",
    }))
  ) {
    return;
  }
  await writer.run(() => competitionsApi.archivePast(), {
    done: (r) => `📦 ${r.archived.length} compétition${plural(r.archived.length)} archivée${plural(r.archived.length)}.`,
  });
}

const listLine = computed(() => {
  if (!competitions.data.value) {
    return competitions.state.value === "loading" ? "⏳ Chargement des compétitions…" : "Aucune donnée des compétitions sur cet appareil.";
  }
  const currentCount = current.value.length;
  const archivedCount = archivedCompetitions.value.length;
  const archivedPart = archivedCount ? ` · ${archivedCount} archivée${plural(archivedCount)}` : "";
  return `${currentCount} compétition${plural(currentCount)}${archivedPart}`;
});
</script>

<template>
  <!-- View mode and creation (masqués sur téléphone quand une fiche est ouverte) -->
  <div :class="['mb-3 flex flex-wrap items-center justify-between gap-2', selected ? 'hidden md:flex' : '']">
    <ViewSwitcher v-model="viewMode" />
    <UiButton
      v-if="canWrite"
      small
      data-testid="create-comp"
      @click="online ? (creating = true) : writer.toast('📴 Hors ligne : création impossible.')"
    >
      ➕ Ajouter une compétition
    </UiButton>
  </div>
  <div
    class="flex flex-col md:grid md:grid-cols-[minmax(0,340px)_minmax(0,1fr)] md:items-start md:gap-4 xl:grid-cols-[320px_minmax(0,1fr)] 2xl:grid-cols-[380px_minmax(0,1fr)]"
  >
    <!-- The competitions: always on desktop (a panel scrolling on its own), on phones until one is opened -->
    <section
      :class="[
        selected ? 'hidden md:block' : '',
        viewMode !== 'cards' ? 'md:col-span-2' : '',
        'order-2 md:order-1 md:col-start-1 md:row-start-1 md:sticky md:top-3 md:max-h-[calc(100dvh-1.5rem)] md:overflow-y-auto md:rounded-xl md:border md:border-slate-200 md:bg-white md:p-3 md:shadow-sm',
      ]"
      aria-label="Liste des compétitions"
    >
      <div v-if="canWrite && pastCompetitions.length" class="mb-2 flex flex-wrap gap-1.5">
        <UiButton variant="muted" small data-testid="archive-past" @click="archivePastCompetitions">
          📦 Archiver les passées ({{ pastCompetitions.length }})
        </UiButton>
      </div>

      <CompetitionFilters
        v-model:season="selectedSeason"
        v-model:search="search"
        v-model:when="when"
        :seasons="seasons"
        :calendar="viewMode === 'calendar'"
      />
      <p class="pt-1 pb-1 mb-2 text-xs text-slate-500" data-testid="comp-count">{{ listLine }}</p>

      <!-- Vue Tableau -->
      <div v-if="viewMode === 'table'" class="mb-3">
        <CompetitionTable
          :competitions="current"
          :can-write="canWrite"
          @open="viewMode = 'cards'"
          @edit="editFromTable"
          @remove="removeFromTable"
        />
      </div>

      <!-- Vue Calendrier -->
      <div v-else-if="viewMode === 'calendar'" class="mb-3">
        <CompetitionCalendar :competitions="calendarCompetitions" :selected-id="selectedId" @open="openFromCalendar" />
      </div>

      <!-- Vue Cartes (par défaut) -->
      <CompetitionCards
        v-else
        :competitions="current"
        :archived="archivedCompetitions"
        :loaded="competitions.data.value !== null"
        :filtered="filtered"
        :selected-id="selected?.id"
      />
    </section>

    <CompetitionDetail
      v-if="selected && viewMode === 'cards'"
      :key="selected.id"
      :competition="selected"
      :rows="rows"
      :members="members.data.value ?? []"
      :coaches="coaches.data.value ?? []"
      :can-write="canWrite"
      :staff="staff"
      :contacts-shown="contactsShown"
      :outbox="outbox"
      :uid="uid"
      class="order-1 min-w-0 md:order-2 md:col-start-2 md:row-start-1"
    />
    <div
      v-else-if="viewMode === 'cards'"
      class="order-1 flex min-w-0 flex-col gap-3 md:order-2 md:col-start-2 md:row-start-1"
      data-testid="stats-no-selection"
    >
      <CompetitionStats :competitions="seasonCompetitions" :today="today" />

      <div class="hidden rounded-xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-slate-500 md:block">
        <p class="m-0 text-sm font-medium">
          {{
            selectedId && competitions.data.value
              ? "Compétition introuvable."
              : "Sélectionnez une compétition dans la liste pour afficher ses détails et gérer ses compétiteurs."
          }}
        </p>
      </div>
    </div>
  </div>

  <UiDialog v-model:open="creating" title="➕ Nouvelle compétition" wide data-testid="create-dialog">
    <CompetitionForm
      v-if="creating"
      :coaches="coaches.data.value ?? []"
      :busy="writer.busy.value"
      @save="create"
      @cancel="creating = false"
    />
  </UiDialog>

  <UiDialog v-model:open="editDialogOpen" :title="`✏️ Modifier : ${editingCompetition?.nom}`" wide data-testid="edit-dialog">
    <CompetitionForm
      v-if="editingCompetition"
      :competition="editingCompetition"
      :coaches="coaches.data.value ?? []"
      :busy="writer.busy.value"
      @save="saveFromTable"
      @cancel="editingCompetition = null"
    />
  </UiDialog>
</template>
