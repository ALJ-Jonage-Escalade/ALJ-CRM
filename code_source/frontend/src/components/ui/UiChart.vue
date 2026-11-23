<script setup lang="ts">
/* A pie, bar or line chart (Chart.js, only the parts used are registered) with its figures in a visually hidden table: screen
   readers read the table, and the tests too (jsdom draws no canvas). A click anywhere on the chart emits `select`.
   Long axis labels keep their beginning; hovering a bar, a slice or an axis label highlights it and writes its whole
   label and figures on the line under the chart (instead of a floating tooltip). A pie starts with its first slice on
   the left. */
import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PieController,
  PointElement,
} from "chart.js";
import { onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from "vue";
import { figure, hoverText, shortLabel } from "./chartText";

Chart.register(
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Legend,
  LineController,
  LineElement,
  PieController,
  PointElement,
);

export interface ChartDataset {
  label: string;
  data: number[];
  /** One colour per value (a pie), or one for the whole dataset (a bar series, a line); CSS colours. */
  colors: string | string[];
  /** A line drawn dashed (a total next to its parts) */
  dashed?: boolean;
}

const props = withDefaults(
  defineProps<{
    type: "pie" | "bar" | "line";
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
/** The whole label and figures of the hovered value, empty when nothing is hovered. */
const hovered = ref("");

/** Characters an axis label may hold: Chart.js gives an axis half of the chart's width (about 7 px per character). */
const AXIS_SHARE = 0.5;
const CHARACTER_WIDTH = 7;

/** A pie turns so that its first slice (the largest when sorted) is centred on the left, the others following clockwise;
    Chart.js counts degrees clockwise from the top. */
function pieRotation(data: readonly number[]): number {
  const total = data.reduce((sum, value) => sum + value, 0);
  const firstAngle = total ? ((data[0] ?? 0) / total) * 360 : 0;
  return 270 - firstAngle / 2;
}

function chartData() {
  return {
    labels: props.labels,
    datasets: props.datasets.map((dataset) => ({
      label: dataset.label,
      data: dataset.data,
      backgroundColor: dataset.colors,
      borderColor: props.type === "pie" ? "#fff" : dataset.colors, // white between the slices of a pie
      borderDash: dataset.dashed ? [6, 4] : [],
      ...(props.type === "pie" ? { rotation: pieRotation(dataset.data) } : {}),
    })),
  };
}

onMounted(() => {
  const context = canvas.value?.getContext("2d");
  if (!context) {
    return; // no canvas support (tests): the table still holds the figures
  }
  const scale = { stacked: props.stacked, beginAtZero: true };
  const categoryScale = {
    ...scale,
    ticks: {
      callback(this: { chart: Chart; getLabelForValue: (value: number) => string }, value: number | string) {
        const width = this.chart.width * AXIS_SHARE;
        return shortLabel(this.getLabelForValue(Number(value)), Math.max(6, Math.floor(width / CHARACTER_WIDTH)));
      },
    },
  };
  const categoryAxis = props.horizontal ? "y" : "x";
  chart = new Chart(context, {
    type: props.type,
    data: chartData(),
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: props.horizontal ? "y" : "x",
      scales: props.type === "pie" ? {} : { x: scale, y: scale, [categoryAxis]: categoryScale },
      events: ["click"], // the hover is ours (it also covers the axis labels, outside Chart.js' chart area)
      plugins: { legend: { display: props.type === "pie" || props.datasets.length > 1, position: "bottom" } },
      onClick: () => emit("select"),
    },
  });
  canvas.value?.addEventListener("mousemove", hover);
  canvas.value?.addEventListener("mouseleave", leave);
});

/** A slice under the pointer; for bars and lines, the row (or column) of the pointer, axis label included. */
function hover(event: MouseEvent) {
  if (!chart) {
    return;
  }
  const elements =
    props.type === "pie"
      ? chart.getElementsAtEventForMode(event, "nearest", { intersect: true }, false)
      : chart.getElementsAtEventForMode(event, "index", { intersect: false, axis: props.horizontal ? "y" : "x" }, false);
  const index = elements[0]?.index;
  const text = index === undefined ? "" : hoverText(props.labels[index] ?? "", props.datasets, index, props.unit);
  if (text === hovered.value) {
    return; // same value still hovered: no redraw, the highlight stays still
  }
  hovered.value = text;
  chart.setActiveElements(elements.map(({ datasetIndex, index: elementIndex }) => ({ datasetIndex, index: elementIndex })));
  chart.update();
}

function leave() {
  hovered.value = "";
  chart?.setActiveElements([]);
  chart?.update();
}

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

onBeforeUnmount(() => {
  canvas.value?.removeEventListener("mousemove", hover);
  canvas.value?.removeEventListener("mouseleave", leave);
  chart?.destroy();
});
</script>

<template>
  <figure class="flex h-64 flex-col">
    <div class="relative min-h-0 flex-1">
      <canvas ref="canvas" role="img" :aria-label="title" class="cursor-pointer" />
    </div>
    <figcaption class="h-5 truncate pt-1 text-xs font-medium text-slate-600" aria-hidden="true">{{ hovered }}</figcaption>
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
          <td v-for="dataset in datasets" :key="dataset.label">{{ figure(dataset.data[index], unit) }}</td>
        </tr>
      </tbody>
    </table>
  </figure>
</template>
