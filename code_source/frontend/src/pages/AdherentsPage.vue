<script setup lang="ts">
/* Adhérents (coaches and admins): the members of a season, filtered by slot / tariff, status and search, sorted,
   paged, exported to CSV, and the member record in a collapsible side panel: read and e-mailed by coaches and admins,
   edited and sent its payment certificate by admins (in a dialog over the page), who also add members. The panel shows
   the member of the URL (?id=<user_id>&saison=…&achat=…: recordQuery), or else the first row of the list as shown; a
   click on a row selects it (history entry: Back goes to the previous member) and opens the panel again if it was
   collapsed. A record can be linked and the former page's links still open it; ?ajout=1 opens the add form. Online
   only: the list is polled every 20 s (ETag, 304 when unchanged) and the record is read from it; nothing is kept on
   the device, only the filters (without the search) and whether the panel is open are remembered. */
import { computed, ref, useTemplateRef, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import AppShell from "../components/AppShell.vue";
import DataTable from "../components/DataTable.vue";
import type { DataColumn } from "../components/dataTable";
import UiBadge from "../components/ui/UiBadge.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiCard from "../components/ui/UiCard.vue";
import UiSidePanel from "../components/ui/UiSidePanel.vue";
import UiToast from "../components/ui/UiToast.vue";
import { useSyncedResource } from "../composables/syncedResource";
import { useToast } from "../composables/toast";
import { membersRead } from "../services/members";
import { csvBlob } from "../lib/csv";
import { saveFile } from "../lib/download";
import { formatDayText } from "../lib/format";
import { isAdmin } from "../lib/roles";
import MemberActionsDialog from "./adherents/MemberActionsDialog.vue";
import MemberAddDialog from "./adherents/MemberAddDialog.vue";
import MemberRecord from "./adherents/MemberRecord.vue";
import {
  allowedTarifs,
  checkAll,
  collator,
  countSummary,
  creneauItems,
  csvName,
  csvRows,
  dateValue,
  diplomes,
  diplomeWeight,
  filterMembers,
  groupChecked,
  isCompetitor,
  loadFilters,
  loadPanelOpen,
  OTHER_PREFIX,
  otherChecked,
  recordMember,
  recordQuery,
  saveFilters,
  savePanelOpen,
  statusChips,
  statusColor,
  tarifCounts,
  type CreneauItem,
  type Member,
} from "./adherents/members";
import { tarifChoices, type RecordAction, type RecordActions } from "./adherents/record";
import { telHref } from "../lib/text";

const toast = useToast();
const route = useRoute();
const router = useRouter();

const filters = ref(loadFilters());
watch(filters, (f) => saveFilters(f), { deep: true });

// Data: the seasons, and the members of the chosen season (the active one when none is chosen)
const seasons = useSyncedResource("seasons", { path: "/api/seasons" }, { offline: false, intervalMs: 60_000 });
const members = useSyncedResource("members", () => membersRead(filters.value.season), { offline: false });
// A season that no longer exists (remembered from an earlier visit): back to the active one
watch(members.httpStatus, (status) => {
  if (status === 404 && filters.value.season) {
    filters.value.season = "";
  }
});

const membersList = computed(() => members.data.value);
const season = computed(() => membersList.value?.season ?? filters.value.season);
const all = computed<readonly Member[]>(() => membersList.value?.members ?? []);
const items = computed(() => creneauItems(membersList.value?.creneaux ?? []));
const counts = computed(() => tarifCounts(all.value, items.value));
const otherTarifs = computed(() => Object.keys(counts.value.others).sort((a, b) => a.localeCompare(b, "fr")));
const competitorsOnly = ref(false);
const competitorCount = computed(() => all.value.filter(isCompetitor).length);
const shown = computed(() => {
  const filtered = filterMembers(all.value, filters.value, allowedTarifs(items.value, counts.value, filters.value));
  return competitorsOnly.value ? filtered.filter(isCompetitor) : filtered;
});
const chips = computed(() => statusChips(all.value));
const summary = computed(() =>
  membersList.value ? countSummary(shown.value.length, all.value.length, season.value) : "Chargement des données…",
);

const syncInfo = computed(() => {
  const state = members.state.value;
  if (state === "offline") {
    return "📴 Hors ligne : liste non actualisée";
  }
  if (members.httpStatus.value === 403) {
    return "🔒 Accès réservé aux coachs";
  }
  if (state === "error") {
    return "⚠️ Chargement des adhérents impossible — nouvel essai automatique";
  }
  return "";
});

function chooseSeason(name: string): void {
  filters.value.season = name;
}

// Slot / tariff filter
const filterOpen = ref(false);

function toggleGroup(it: CreneauItem, on: boolean): void {
  filters.value.groups[it.raw] = on;
}

function toggleOther(tarif: string, on: boolean): void {
  filters.value.others[OTHER_PREFIX + tarif] = on;
}

function setAll(on: boolean): void {
  filters.value = checkAll(filters.value, items.value, counts.value, on);
}

function toggleStatus(value: string): void {
  filters.value.status = filters.value.status === value ? "" : value;
}

// The table goes back to its first page when the filters or the season change
const resetKey = computed(() => [
  season.value,
  filters.value.status,
  filters.value.search,
  filters.value.groups,
  filters.value.others,
  competitorsOnly.value,
]);

const COLUMNS: DataColumn<Member>[] = [
  {
    id: "last_name",
    label: "Nom",
    value: (m) => (isCompetitor(m) ? `🏆 ${m.last_name}` : m.last_name),
    // The trophy is only shown: the column still sorts by name
    compare: (a, b) => collator.compare(a.last_name, b.last_name),
    class: "font-bold",
  },
  { id: "first_name", label: "Prénom", value: (m) => m.first_name },
  {
    id: "order_date",
    label: "Date d'inscription",
    value: (m) => formatDayText(m.order_date),
    compare: (a, b) => dateValue(a.order_date) - dateValue(b.order_date),
    descFirst: true,
    class: "whitespace-nowrap text-slate-500",
  },
  {
    id: "diplome",
    label: "Diplôme",
    title: "Diplômes & autonomie (🔴 Badge rouge, 🧗 Autonomie bloc, 🟠 Passeport orange)",
    value: (m) => diplomeWeight(m),
    compare: (a, b) => diplomeWeight(a) - diplomeWeight(b) || collator.compare(a.last_name, b.last_name),
    descFirst: true,
    class: "text-center",
  },
  { id: "status_norm", label: "Statut", value: (m) => m.status_norm },
  { id: "creneau_groupe", label: "Créneau", value: (m) => m.creneau_groupe, class: "text-slate-500" },
  { id: "city", label: "Ville", value: (m) => m.city, class: "text-slate-500" },
  { id: "email_primary", label: "E-mail", value: (m) => m.email_primary },
  { id: "phone", label: "Téléphone", value: (m) => m.phone, class: "whitespace-nowrap" },
  { id: "licence_ffme", label: "Licence", value: (m) => m.licence_ffme, class: "text-slate-500" },
];

// The CSV holds the list shown, every page, in the table's order
const tableRef = ref<{ sortedRows(): Member[] } | null>(null);
function exportCsv(): void {
  if (!shown.value.length) {
    toast.show("⚠️ Aucun adhérent à exporter avec les filtres actuels.");
    return;
  }
  saveFile(csvBlob(csvRows(tableRef.value?.sortedRows() ?? shown.value)), csvName(season.value));
}

// ---------------------------------------------------------------- Member record (side panel)

const queryText = (name: string) => (typeof route.query[name] === "string" ? route.query[name] : "");
const recordId = computed(() => queryText("id"));
// A record of another season (link): the list follows it
watch(
  () => queryText("saison"),
  (wanted) => {
    if (wanted && wanted !== season.value) {
      filters.value.season = wanted;
    }
  },
  { immediate: true },
);
const recordReady = computed(() => !!membersList.value && (!queryText("saison") || membersList.value.season === queryText("saison")));
// The member of the URL, even when the filters hide it, or else the first row of the list as shown (sorted)
const record = computed(() => {
  if (!recordReady.value) {
    return undefined;
  }
  if (recordId.value) {
    return recordMember(all.value, recordId.value, queryText("achat") || undefined);
  }
  return tableRef.value?.sortedRows()[0];
});
const selectedKey = computed(() => (record.value ? String(record.value.purchase_id) : ""));

// Columns the panel already shows, hidden from the table while it is open to make room. Adjust from users' feedback.
const PANEL_HIDDEN_COLUMNS = ["city", "email_primary", "phone"];

const panelOpen = ref(loadPanelOpen());
watch(panelOpen, (open) => savePanelOpen(open));
// A member chosen (row click, link, new member): the panel opens again
watch(
  recordId,
  (id) => {
    if (id) {
      panelOpen.value = true;
    }
  },
  { immediate: true },
);

function select(m: Member): void {
  panelOpen.value = true; // also for the member already in the URL, whose recordId does not change
  void router.push({ query: recordQuery(m) });
}

// The record's actions open a dialog over the page (MemberActionsDialog)
const actions = useTemplateRef<RecordActions>("actions");
async function openAction(next: RecordAction): Promise<void> {
  // The first row shown by default is pinned in the URL first: a member added by a poll and sorted above it would
  // otherwise change the record, which closes the form and loses what was typed
  if (!recordId.value && record.value) {
    await router.replace({ query: { ...route.query, ...recordQuery(record.value) } });
  }
  await actions.value?.open(next);
}

const tarifs = computed(() => tarifChoices(membersList.value?.creneaux ?? [], all.value));

// Add (?ajout=1)
const adding = computed({
  get: () => queryText("ajout") === "1",
  set: (open) => {
    if (!open) {
      const rest = Object.fromEntries(Object.entries(route.query).filter(([k]) => k !== "ajout"));
      void router.replace({ query: rest });
    }
  },
});
/** Selects the new member in the panel (its membership is the one of the new order). */
async function added(orderRef: string): Promise<void> {
  await members.refresh();
  const member = all.value.find((m) => m.order_ref === orderRef);
  void router.replace({ query: member ? recordQuery(member) : {} });
}

const chip = (active: boolean) => [
  "cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold",
  active ? "border-accent bg-accent text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
];
const linkButton =
  "inline-flex items-center gap-1.5 rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 no-underline hover:bg-slate-300";
</script>

<template>
  <AppShell v-slot="{ role }" page="adherents" title="Adhérents" :sync="syncInfo">
    <UiCard class="mb-3">
      <div class="flex flex-wrap items-center gap-2">
        <select
          :value="season"
          data-testid="season-select"
          aria-label="Saison"
          class="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[12.5px]"
          @change="chooseSeason(($event.target as HTMLSelectElement).value)"
        >
          <option v-if="!seasons.data.value && season" :value="season">{{ season }}</option>
          <option v-for="s in seasons.data.value?.seasons ?? []" :key="s" :value="s">
            {{ s }}{{ s === seasons.data.value?.active ? " (active)" : "" }}
          </option>
        </select>
        <input
          v-model="filters.search"
          type="search"
          data-testid="member-search"
          aria-label="Rechercher un adhérent"
          placeholder="🔍 Rechercher (nom, prénom, ville, tarif, licence, e-mail, tél.)…"
          class="min-w-0 flex-1 basis-60 rounded-lg border border-slate-300 px-2.5 py-1.5 text-[12.5px]"
        />
        <UiButton
          :variant="filterOpen ? 'primary' : 'muted'"
          small
          data-testid="filter-toggle"
          :aria-expanded="filterOpen"
          @click="filterOpen = !filterOpen"
        >
          📂 Créneaux / Tarifs
        </UiButton>
        <UiButton variant="muted" small data-testid="export-csv" title="Télécharger la liste affichée en fichier CSV" @click="exportCsv">
          📥 Export CSV
        </UiButton>
        <a href="/bureau/outils/ffme" :class="linkButton" data-testid="export-ffme" title="Ouvrir l'export officiel FFME">🇫🇷 Export FFME</a>
        <a v-if="isAdmin(role)" href="/bureau/outils/ffme-import" :class="linkButton" title="Importer la liste Excel des licenciés FFME">
          📥 Import FFME
        </a>
        <UiButton
          v-if="!panelOpen"
          variant="muted"
          small
          data-testid="panel-open"
          aria-controls="record-panel"
          :aria-expanded="false"
          title="Afficher la fiche de l'adhérent sélectionné"
          @click="panelOpen = true"
        >
          ⇤ Fiche
        </UiButton>
        <RouterLink
          v-if="isAdmin(role)"
          :to="{ query: { ...route.query, ajout: '1' } }"
          data-testid="member-add"
          class="inline-flex items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1.5 text-xs font-bold text-white no-underline hover:bg-accent-dark"
          title="Ajouter un adhérent à la saison affichée"
        >
          ➕ Ajouter un adhérent
        </RouterLink>
      </div>

      <div v-if="filterOpen" data-testid="filter-box" class="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
        <div class="mb-1.5 flex flex-wrap items-center justify-between gap-2">
          <b>🧗 Sélection des créneaux & tarifs</b>
          <div class="flex gap-1.5">
            <UiButton variant="muted" small data-testid="filter-all" @click="setAll(true)">Tout cocher</UiButton>
            <UiButton variant="muted" small data-testid="filter-none" @click="setAll(false)">Tout décocher</UiButton>
          </div>
        </div>
        <p class="mb-2 text-[11.5px] text-slate-500">
          Cochez ou décochez les groupes pour affiner l'affichage. Par défaut, les listes d'attente sont exclues.
        </p>
        <div class="grid gap-x-4 sm:grid-cols-2 lg:grid-cols-3">
          <template v-for="it in items" :key="`${it.kind}:${it.raw}`">
            <div v-if="it.kind === 'section'" class="col-span-full mt-2 text-xs font-bold text-slate-700">📁 {{ it.label }}</div>
            <div v-else-if="it.kind === 'sub'" class="col-span-full mt-1 pl-2 text-[11.5px] font-semibold text-slate-500">
              📂 {{ it.label }}
            </div>
            <label v-else data-testid="filter-group" class="flex cursor-pointer items-center gap-2 py-0.5 text-[12.5px]">
              <input
                type="checkbox"
                class="accent-accent"
                :checked="groupChecked(filters, it)"
                @change="toggleGroup(it, ($event.target as HTMLInputElement).checked)"
              />
              <span class="min-w-0 flex-1 truncate" :title="it.raw">{{ it.label }}</span>
              <span data-testid="filter-count" class="rounded-full bg-slate-200 px-2 text-[11px] font-semibold text-slate-600">
                {{ counts.groups[it.raw] ?? 0 }}
              </span>
            </label>
          </template>
          <template v-if="otherTarifs.length">
            <div class="col-span-full mt-2 text-xs font-bold text-slate-700">📁 Autres tarifs (hors créneau)</div>
            <label
              v-for="t in otherTarifs"
              :key="t"
              data-testid="filter-group"
              class="flex cursor-pointer items-center gap-2 py-0.5 text-[12.5px]"
            >
              <input
                type="checkbox"
                class="accent-accent"
                :checked="otherChecked(filters, t)"
                @change="toggleOther(t, ($event.target as HTMLInputElement).checked)"
              />
              <span class="min-w-0 flex-1 truncate">{{ t }}</span>
              <span data-testid="filter-count" class="rounded-full bg-slate-200 px-2 text-[11px] font-semibold text-slate-600">
                {{ counts.others[t] }}
              </span>
            </label>
          </template>
        </div>
      </div>

      <div class="mt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2">
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="c in chips"
            :key="c.value"
            type="button"
            :data-testid="`status-${c.value || 'all'}`"
            :aria-pressed="filters.status === c.value"
            :class="chip(filters.status === c.value)"
            @click="toggleStatus(c.value)"
          >
            {{ c.label }} ({{ c.count }})
          </button>
          <button
            type="button"
            :class="[
              'cursor-pointer rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors',
              competitorsOnly ? 'border-purple-600 bg-purple-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
            ]"
            data-testid="filter-competitors"
            @click="competitorsOnly = !competitorsOnly"
          >
            🏆 Compétiteurs ({{ competitorCount }})
          </button>
        </div>
        <span data-testid="member-count" class="text-xs text-slate-500">{{ summary }}</span>
      </div>
    </UiCard>

    <div class="flex flex-col gap-3 lg:flex-row lg:items-start">
      <DataTable
        ref="tableRef"
        class="min-w-0 flex-1"
        :rows="shown"
        :columns="COLUMNS"
        :row-key="(m: Member) => String(m.purchase_id)"
        :sort="{ id: 'last_name' }"
        :reset-key="resetKey"
        :hidden="panelOpen ? PANEL_HIDDEN_COLUMNS : []"
        :selected-key="selectedKey"
        :on-row-click="select"
        label="Adhérents"
        :empty="membersList ? 'Aucun adhérent ne correspond aux filtres actifs.' : 'Chargement en cours…'"
      >
        <template #cell-last_name="{ row }">
          <RouterLink
            :to="{ query: recordQuery(row) }"
            data-testid="member-record"
            class="font-bold text-slate-800 no-underline hover:text-accent hover:underline"
            title="Ouvrir la fiche adhérent"
            @click="panelOpen = true"
          >
            {{ row.last_name }}
          </RouterLink>
        </template>
        <template #cell-order_date="{ value }">{{ value || "—" }}</template>
        <template #cell-diplome="{ row }">
          <span v-for="d in diplomes(row)" :key="d.type" :title="d.label" class="cursor-help px-0.5">{{ d.icon }}</span>
          <span v-if="!diplomes(row).length" class="text-slate-400">—</span>
        </template>
        <template #cell-status_norm="{ row }">
          <UiBadge :color="statusColor(row.status_norm)">{{ row.status_norm || "—" }}</UiBadge>
        </template>
        <template #cell-creneau_groupe="{ value }">{{ value || "—" }}</template>
        <template #cell-city="{ value }">{{ value || "—" }}</template>
        <template #cell-email_primary="{ row }">
          <a v-if="row.email_primary" :href="`mailto:${row.email_primary}`">{{ row.email_primary }}</a>
          <template v-else>—</template>
        </template>
        <template #cell-phone="{ row }">
          <a v-if="row.phone" :href="telHref(row.phone)">{{ row.phone }}</a>
          <template v-else>—</template>
        </template>
        <template #cell-licence_ffme="{ value }">{{ value || "—" }}</template>

        <template #card="{ row }">
          <div class="flex items-start justify-between gap-2">
            <RouterLink
              :to="{ query: recordQuery(row) }"
              data-testid="member-record"
              class="min-w-0 font-bold text-slate-800 no-underline"
              @click="panelOpen = true"
            >
              {{ row.last_name }} {{ row.first_name }}
            </RouterLink>
            <UiBadge :color="statusColor(row.status_norm)" class="shrink-0">{{ row.status_norm || "—" }}</UiBadge>
          </div>
          <div class="mt-0.5 text-xs text-slate-500">
            {{ [row.creneau_groupe, row.city].filter(Boolean).join(" · ") || "—" }}
            <span v-for="d in diplomes(row)" :key="d.type" :title="d.label" class="pl-1">{{ d.icon }}</span>
          </div>
          <div class="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[12.5px]">
            <a v-if="row.phone" :href="telHref(row.phone)">📞 {{ row.phone }}</a>
            <a v-if="row.email_primary" :href="`mailto:${row.email_primary}`" class="min-w-0 break-all">✉️ {{ row.email_primary }}</a>
            <span v-if="row.licence_ffme" class="text-slate-500">🪪 {{ row.licence_ffme }}</span>
          </div>
        </template>
      </DataTable>

      <UiSidePanel
        id="record-panel"
        v-model:open="panelOpen"
        title="👤 Fiche adhérent"
        class="order-first lg:order-none"
        data-testid="record-panel"
      >
        <p v-if="!record" data-testid="record-missing" class="text-[13px] text-slate-500">
          {{
            !recordReady
              ? "Chargement de la fiche…"
              : recordId
                ? `Adhérent introuvable dans la saison ${season}.`
                : "Aucun adhérent à afficher."
          }}
        </p>
        <MemberRecord
          v-else
          :member="record"
          :admin="isAdmin(role)"
          compact
          @email="openAction('email')"
          @attestation="openAction('attestation')"
          @edit="openAction('edit')"
        >
          <template #status>
            <UiBadge :color="statusColor(record.status_norm)">{{ record.status_norm || "—" }}</UiBadge>
          </template>
        </MemberRecord>
      </UiSidePanel>
    </div>

    <MemberActionsDialog
      v-if="record"
      ref="actions"
      :member="record"
      :admin="isAdmin(role)"
      :tarifs="tarifs"
      @changed="members.refresh()"
      @notify="toast.show"
    />
    <MemberAddDialog
      v-if="isAdmin(role)"
      v-model:open="adding"
      :season="season"
      :members="all"
      :tarifs="tarifs"
      @created="added"
      @notify="toast.show"
    />
    <UiToast :message="toast.message.value" />
  </AppShell>
</template>
