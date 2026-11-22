<script setup lang="ts">
/* A member chart of Outils › Statistiques: the members of the season per value of a dimension, and its breakdown
   (stacked bars, in counts or percent of each bar) shown under it by « Détail » or a click on the chart. */
import { computed, ref } from "vue";
import UiCard from "../../../components/ui/UiCard.vue";
import UiChart from "../../../components/ui/UiChart.vue";
import { HEX } from "../../../components/ui/palette";
import { breakdown, CATEGORY_COLORS, countBy, type Dimension, type SeasonMember } from "./memberStats";

const props = withDefaults(
  defineProps<{
    /** Names the testids: chart-<id>, detail-<id>, chart-<id>-detail */
    id: string;
    title: string;
    members: SeasonMember[];
    dimension: Dimension;
    type: "pie" | "bar";
    horizontal?: boolean;
    /** The breakdown: `series` per value of `bars` */
    detail: { series: Dimension; bars: Dimension; title: string };
    note?: string;
  }>(),
  { horizontal: false, note: "" },
);

/** Colours of the values without a colour of their own (groups, cities…), in turn. */
const CYCLE = [HEX.blue, HEX.orange, HEX.teal, HEX.violet, HEX.green, HEX.pink, HEX.sky, HEX.amber, HEX.indigo, HEX.red];
const colorOf = (label: string, index: number) => CATEGORY_COLORS[label] ?? CYCLE[index % CYCLE.length] ?? HEX.blue;

const open = ref(false);
const mode = ref<"count" | "percent">("count");

const slices = computed(() => countBy(props.members, props.dimension));
const datasets = computed(() => [
  {
    label: "Adhérents",
    data: slices.value.map((slice) => slice.count),
    colors: props.type === "pie" ? slices.value.map((slice, index) => colorOf(slice.label, index)) : HEX.blue,
  },
]);
const detailBars = computed(() => breakdown(props.members, props.detail.series, props.detail.bars, mode.value));
const detailDatasets = computed(() =>
  detailBars.value.series.map((serie, index) => ({ label: serie.label, data: serie.values, colors: colorOf(serie.label, index) })),
);
</script>

<template>
  <UiCard>
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500">{{ title }}</h3>
      <button
        type="button"
        class="text-xs font-semibold text-blue-700 hover:underline"
        :aria-expanded="open"
        :data-testid="`detail-${id}`"
        @click="open = !open"
      >
        Détail {{ open ? "▾" : "›" }}
      </button>
    </div>
    <UiChart
      :type="type"
      :title="title"
      :horizontal="horizontal"
      :labels="slices.map((slice) => slice.label)"
      :datasets="datasets"
      :data-testid="`chart-${id}`"
      @select="open = !open"
    />
    <p v-if="note" class="mt-2 text-[11px] italic text-slate-400">{{ note }}</p>
    <div v-if="open" class="mt-4 border-t border-slate-100 pt-3">
      <div class="flex items-center justify-between mb-2">
        <h4 class="text-xs font-semibold text-slate-600">{{ detail.title }}</h4>
        <div class="flex gap-1 text-[11px] font-semibold" role="group" aria-label="Unité">
          <button
            type="button"
            :class="['rounded px-2 py-0.5', mode === 'count' ? 'bg-slate-700 text-white' : 'bg-slate-100 text-slate-600']"
            :aria-pressed="mode === 'count'"
            :data-testid="`detail-${id}-count`"
            @click="mode = 'count'"
          >
            Nombre
          </button>
          <button
            type="button"
            :class="['rounded px-2 py-0.5', mode === 'percent' ? 'bg-slate-700 text-white' : 'bg-slate-100 text-slate-600']"
            :aria-pressed="mode === 'percent'"
            :data-testid="`detail-${id}-percent`"
            @click="mode = 'percent'"
          >
            %
          </button>
        </div>
      </div>
      <UiChart
        type="bar"
        stacked
        :horizontal="detailBars.labels.length > 6"
        :title="detail.title"
        :unit="mode === 'percent' ? '%' : ''"
        :labels="detailBars.labels"
        :datasets="detailDatasets"
        :data-testid="`chart-${id}-detail`"
      />
    </div>
  </UiCard>
</template>
