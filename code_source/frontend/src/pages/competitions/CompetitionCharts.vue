<script setup lang="ts">
import { computed } from "vue";
import type { Competition, Row } from "./competitions";

const props = defineProps<{
  competition: Competition;
  rows: readonly Row[];
}>();

// 1. Répartition par catégorie d'âge
const categoryCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const r of props.rows) {
    const cat = r.categorie_ffme?.trim() || "Non renseignée";
    counts[cat] = (counts[cat] || 0) + 1;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1]);
});

// 2. Répartition par discipline
const disciplineCounts = computed(() => {
  const counts: Record<string, number> = {};
  const compType = (props.competition.type || "Bloc").trim();
  for (const r of props.rows) {
    const disc = r.group || compType;
    counts[disc] = (counts[disc] || 0) + 1;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1]);
});

const PALETTE = ["#3B82F6", "#8B5CF6", "#EC4899", "#F59E0B", "#10B981", "#6366F1", "#14B8A6", "#F97316"];

// Calcul des parts du camembert (SVG Pie)
const totalCategories = computed(() => categoryCounts.value.reduce((sum, [, n]) => sum + n, 0));

const pieSlices = computed(() => {
  const total = totalCategories.value;
  if (!total) {
    return [];
  }
  let cumulative = 0;
  return categoryCounts.value.map(([label, count], i) => {
    const startAngle = (cumulative / total) * 360;
    cumulative += count;
    const endAngle = (cumulative / total) * 360;
    const color = PALETTE[i % PALETTE.length];

    // Calcul arc SVG (r = 40, center = 50, 50)
    const x1 = 50 + 40 * Math.cos((Math.PI * (startAngle - 90)) / 180);
    const y1 = 50 + 40 * Math.sin((Math.PI * (startAngle - 90)) / 180);
    const x2 = 50 + 40 * Math.cos((Math.PI * (endAngle - 90)) / 180);
    const y2 = 50 + 40 * Math.sin((Math.PI * (endAngle - 90)) / 180);
    const largeArc = endAngle - startAngle > 180 ? 1 : 0;

    const path =
      categoryCounts.value.length === 1
        ? "M 50 10 A 40 40 0 1 1 49.99 10 Z"
        : `M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z`;

    const percent = Math.round((count / total) * 100);
    return { label, count, percent, color, path };
  });
});

const maxDisciplineCount = computed(() => Math.max(...disciplineCounts.value.map(([, n]) => n), 1));
</script>

<template>
  <div v-if="rows.length" class="mb-4 grid gap-4 md:grid-cols-2" data-testid="competition-charts">
    <!-- Graphique 1 : Camembert catégories d'âge -->
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col justify-between">
      <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">🥧 Répartition par catégorie d'âge</h3>
      <div class="flex items-center gap-4 flex-wrap sm:flex-nowrap">
        <svg viewBox="0 0 100 100" class="size-32 shrink-0 drop-shadow-xs">
          <path
            v-for="slice in pieSlices"
            :key="slice.label"
            :d="slice.path"
            :fill="slice.color"
            class="transition-opacity hover:opacity-80"
          />
        </svg>
        <div class="flex flex-col gap-1.5 text-xs flex-1 min-w-32">
          <div v-for="slice in pieSlices" :key="slice.label" class="flex items-center justify-between gap-2">
            <span class="flex items-center gap-1.5 truncate">
              <span class="size-2.5 rounded-full shrink-0" :style="{ backgroundColor: slice.color }" />
              <span class="truncate font-medium text-slate-700">{{ slice.label }}</span>
            </span>
            <span class="font-bold text-slate-900 shrink-0">{{ slice.count }} ({{ slice.percent }}%)</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Graphique 2 : Barres par discipline / créneau -->
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col justify-between">
      <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">📊 Répartition par discipline</h3>
      <div class="flex flex-col gap-2.5">
        <div v-for="([label, count], i) in disciplineCounts" :key="label" class="text-xs">
          <div class="flex justify-between font-medium text-slate-700 mb-1">
            <span class="truncate">{{ label }}</span>
            <span class="font-bold text-slate-900">{{ count }}</span>
          </div>
          <div class="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-300"
              :style="{
                width: `${(count / maxDisciplineCount) * 100}%`,
                backgroundColor: PALETTE[i % PALETTE.length],
              }"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
