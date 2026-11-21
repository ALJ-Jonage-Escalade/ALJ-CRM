<script setup lang="ts">
/* A pie or bar chart (Chart.js, only the parts used are registered) with its figures in a visually hidden table: screen
   readers read the table, and the tests too (jsdom draws no canvas). A click anywhere on the chart emits `select`. */
import { ArcElement, BarController, BarElement, CategoryScale, Chart, Legend, LinearScale, PieController, Tooltip } from "chart.js";
import { onBeforeUnmount, onMounted, useTemplateRef, watch } from "vue";

Chart.register(ArcElement, BarController, BarElement, CategoryScale, LinearScale, Legend, PieController, Tooltip);

export interface ChartDataset {
  label: string;
  data: number[];
  /** One colour per value (a pie), or one for the whole dataset (a bar series); CSS colours. */
  colors: string | string[];
}

const props = withDefaults(
  defineProps<{
    type: "pie" | "bar";
    title: string;
    labels: string[];
    datasets: ChartDataset[];
    /** Bars: horizontal, and stacked (one bar per label, a segment per dataset). */
    horizontal?: boolean;
    stacked?: boolean;
    /** Unit of the values in the table and the tooltips (« % »), none by default. */
    unit?: string;
  }>(),
  { horizontal: false, stacked: false, unit: "" },
);
const emit = defineEmits<{ select: [] }>();

const canvas = useTemplateRef<HTMLCanvasElement>("canvas");
let chart: Chart | null = null;

function chartData() {
  return {
    labels: props.labels,
    datasets: props.datasets.map((dataset) => ({ label: dataset.label, data: dataset.data, backgroundColor: dataset.colors })),
  };
}

onMounted(() => {
  const context = canvas.value?.getContext("2d");
  if (!context) {
    return; // no canvas support (tests): the table still holds the figures
  }
  const scale = { stacked: props.stacked, beginAtZero: true };
  chart = new Chart(context, {
    type: props.type,
    data: chartData(),
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: props.horizontal ? "y" : "x",
      scales: props.type === "bar" ? { x: scale, y: scale } : {},
      plugins: {
        legend: { display: props.type === "pie" || props.datasets.length > 1, position: "bottom" },
        tooltip: { callbacks: props.unit ? { label: (item) => `${item.dataset.label ?? ""} : ${item.formattedValue} ${props.unit}` } : {} },
      },
      onClick: () => emit("select"),
    },
  });
});

watch(
  () => [props.labels, props.datasets],
  () => {
    if (chart) {
      chart.data = chartData();
      chart.update();
    }
  },
  { deep: true },
);

onBeforeUnmount(() => chart?.destroy());

const cell = (value: number | undefined) => `${value ?? 0}${props.unit ? ` ${props.unit}` : ""}`;
</script>

<template>
  <figure class="relative h-64">
    <canvas ref="canvas" role="img" :aria-label="title" class="cursor-pointer" />
    <table class="sr-only">
      <caption>
        {{ title }}
      </caption>
      <thead v-if="datasets.length > 1">
        <tr>
          <th />
          <th v-for="dataset in datasets" :key="dataset.label" scope="col">{{ dataset.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(label, index) in labels" :key="label">
          <th scope="row">{{ label }}</th>
          <td v-for="dataset in datasets" :key="dataset.label">{{ cell(dataset.data[index]) }}</td>
        </tr>
      </tbody>
    </table>
  </figure>
</template>
