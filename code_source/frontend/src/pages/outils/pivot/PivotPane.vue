<script setup lang="ts">
/* Pivot table (TCD) of the members of a season: vue-pivottable on /api/reports/pivot-records. The layout (fields,
   aggregator, renderer, orders) is kept across season changes and visits (pivotLayout.ts); the value filters go back
   to the defaults on each season change. Loaded with the tab (OutilsPage.vue), not with the map. */
import "vue-pivottable/dist/vue-pivottable.css";
import { VuePivottableUi } from "vue-pivottable";
import { inject, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import UiButton from "../../../components/ui/UiButton.vue";
import { CLIENT_KEY, errorText } from "../../../lib/client";
import { createReportsApi } from "../../../services/reports";
import {
  AGGREGATORS,
  clearLayout,
  defaultModel,
  defaultValueFilter,
  layoutOf,
  loadLayout,
  pivotRow,
  RENDERERS,
  saveLayout,
  type PivotModel,
  type PivotRow,
} from "./pivotLayout";

const props = defineProps<{ season: string }>();
const reportsApi = createReportsApi(inject(CLIENT_KEY)!);

const rows = shallowRef<PivotRow[]>([]);
const loaded = ref(false); // the table stays mounted while another season loads
const status = ref<"loading" | "ready" | "error">("loading");
const message = ref("");
const model = ref<PivotModel>({ ...loadLayout(), valueFilter: defaultValueFilter() });
let request = 0;

async function load(): Promise<void> {
  const mine = ++request; // a slower answer for a former season is dropped
  status.value = "loading";
  try {
    const data = await reportsApi.pivotRecords(props.season);
    if (mine !== request) {
      return;
    }
    rows.value = data.records.map(pivotRow);
    loaded.value = true;
    status.value = "ready";
  } catch (e) {
    if (mine !== request) {
      return;
    }
    message.value = `❌ Impossible de charger le tableau croisé dynamique : ${errorText(e)}`;
    status.value = "error";
  }
}

// Saved at once (a few hundred bytes; the table already groups the events of a drag): a page closed right after a
// change keeps it
function changed(next: PivotModel): void {
  model.value = { ...layoutOf(next), valueFilter: next.valueFilter };
  saveLayout(model.value);
}

function resetLayout(): void {
  clearLayout();
  model.value = defaultModel();
}

watch(
  () => props.season,
  () => {
    // The excluded values name tariffs and statuses of the former season
    model.value = { ...model.value, valueFilter: defaultValueFilter() };
    void load();
  },
);
onMounted(load);
onBeforeUnmount(() => {
  request++;
});
defineExpose({ reload: load });
</script>

<template>
  <div class="mb-2 flex flex-wrap items-center gap-2">
    <p class="min-w-0 flex-1 text-xs text-slate-500">
      Glissez et déposez les étiquettes pour croiser les adhérents (Groupe / Tarif, Sexe, Statut, Âge, Ville…) ; le triangle ▾ d'une
      étiquette filtre ses valeurs.
    </p>
    <UiButton variant="muted" small data-testid="pivot-reset" title="Revenir à la disposition par défaut" @click="resetLayout">
      ↺ Disposition par défaut
    </UiButton>
  </div>
  <div
    v-if="status !== 'ready'"
    data-testid="pivot-status"
    :class="[
      'mb-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px]',
      status === 'error' ? 'text-red-600' : 'text-slate-500',
    ]"
  >
    {{ status === "loading" ? "⏳ Chargement du tableau croisé dynamique…" : message }}
  </div>
  <div v-if="loaded" data-testid="pivot-table" class="alj-pivot overflow-x-auto rounded-xl border border-slate-200 bg-white p-3">
    <VuePivottableUi
      :data="rows"
      :pivot-model="model"
      :aggregators="AGGREGATORS"
      :renderers="RENDERERS"
      locale="fr"
      show-row-total
      show-col-total
      @update:pivot-model="changed"
    />
  </div>
</template>

<style>
/* The package's look (Verdana, large controls) brought to the app's: font, slate borders, club blue headers */
.alj-pivot .pvtUi,
.alj-pivot table.pvtTable {
  font-family: var(--font-sans);
  color: #1e293b;
}
.alj-pivot .pvtUi {
  font-size: 13px;
}
.alj-pivot .pvtAxisContainer,
.alj-pivot .pvtVals,
.alj-pivot .pvtRenderers,
.alj-pivot .pvtUi td.pvtOutput {
  border-color: #e2e8f0;
}
.alj-pivot .pvtDropdown {
  height: 32px;
  border-color: #cbd5e1;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: #334155;
}
.alj-pivot .pvtAxisContainer li {
  padding: 4px 3px;
}
.alj-pivot .pvtAxisContainer li span.pvtAttr {
  background: #f8fafc;
  border: 1px solid #cbd5e1;
  font-size: 12.5px;
}
.alj-pivot table.pvtTable {
  font-size: 13px;
}
.alj-pivot table.pvtTable thead tr th,
.alj-pivot table.pvtTable tbody tr th {
  background-color: #f1f5f9;
  border-color: #cbd5e1;
  color: #334155;
  font-size: 13px;
  padding: 6px 10px;
}
.alj-pivot table.pvtTable thead tr th.pvtAxisLabel {
  background-color: #1e3a8a;
  color: #fff;
}
.alj-pivot table.pvtTable tbody tr td {
  border-color: #cbd5e1;
  color: #475569;
  padding: 6px 10px;
}
.alj-pivot .pvtFilterBox {
  border-color: #cbd5e1;
  border-radius: 8px;
  box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1);
}
.alj-pivot textarea {
  width: 100%;
  min-height: 300px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
}
</style>
