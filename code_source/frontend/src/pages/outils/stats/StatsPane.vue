<script setup lang="ts">
/* Outils › Statistiques, competitions: presence, podiums and competitors of the last seasons, from the competitions on the server. */
import { computed, inject, onMounted, ref } from "vue";
import UiCard from "../../../components/ui/UiCard.vue";
import UiChart from "../../../components/ui/UiChart.vue";
import { HEX } from "../../../components/ui/palette";
import { ApiError, CLIENT_KEY, errorText } from "../../../lib/client";
import { createCompetitionsApi } from "../../../services/competitions";
import type { Competition } from "../../competitions/competitions";
import { competitorGrowthText, participationRateText, seasonStats } from "./stats";

/** Seasons compared on the tiles and the two lists. */
const SEASON_COUNT = 3;

const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
const competitions = ref<Competition[]>([]);
/** Why the statistics are empty when the server refused or failed; offline, they just stay empty. */
const loadError = ref("");

async function load(): Promise<void> {
  loadError.value = "";
  try {
    competitions.value = await competitionsApi.list();
  } catch (e) {
    loadError.value = e instanceof ApiError && e.status === 0 ? "" : errorText(e);
  }
}

onMounted(load);

const seasons = computed(() => seasonStats(competitions.value, SEASON_COUNT));
const participationRate = computed(() => participationRateText(competitions.value));
const podiumCount = computed(() => seasons.value.reduce((sum, season) => sum + season.podiums, 0));
const competitorGrowth = computed(() => competitorGrowthText(seasons.value));
/** The charts read left to right, oldest season first. */
const chartSeasons = computed(() => [...seasons.value].reverse());
const seasonLabels = computed(() => chartSeasons.value.map((season) => season.season));
const podiumDatasets = computed(() =>
  (
    [
      ["Or", "gold", HEX.amber],
      ["Argent", "silver", HEX.slate],
      ["Bronze", "bronze", HEX.orange],
    ] as const
  ).map(([label, medal, colors]) => ({ label, data: chartSeasons.value.map((season) => season[medal]), colors })),
);
const competitorDatasets = computed(() => [
  { label: "Compétiteurs", data: chartSeasons.value.map((season) => season.competitors), colors: HEX.blue },
]);
</script>

<template>
  <div class="flex flex-col gap-4" data-testid="stats-pane">
    <p v-if="loadError" data-testid="stats-load-error" role="alert" class="text-[13px] text-red-700">⚠️ {{ loadError }}</p>
    <div class="grid gap-3 sm:grid-cols-3">
      <UiCard class="text-center">
        <div class="text-2xl font-black text-blue-700" data-testid="kpi-participation">
          {{ participationRate }}
        </div>
        <div class="text-xs font-semibold uppercase text-slate-500 mt-1">Présence des sélectionnés</div>
      </UiCard>
      <UiCard class="text-center">
        <div class="text-2xl font-black text-purple-700" data-testid="kpi-podiums">{{ seasons.length ? podiumCount : "—" }}</div>
        <div class="text-xs font-semibold uppercase text-slate-500 mt-1">Podiums ({{ seasons.length || SEASON_COUNT }} saisons)</div>
      </UiCard>
      <UiCard class="text-center">
        <div class="text-2xl font-black text-emerald-700" data-testid="kpi-growth">{{ competitorGrowth }}</div>
        <div class="text-xs font-semibold uppercase text-slate-500 mt-1">Évolution des compétiteurs</div>
      </UiCard>
    </div>

    <div class="grid gap-4 md:grid-cols-2">
      <UiCard>
        <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">🏆 Podiums par saison</h3>
        <p v-if="!seasons.length" class="text-xs italic text-slate-400">Aucune compétition datée.</p>
        <UiChart
          v-else
          type="bar"
          stacked
          title="Podiums par saison et par médaille"
          data-testid="chart-podiums"
          :labels="seasonLabels"
          :datasets="podiumDatasets"
        />
      </UiCard>

      <UiCard>
        <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">📈 Compétiteurs sélectionnés par saison</h3>
        <p v-if="!seasons.length" class="text-xs italic text-slate-400">Aucune compétition datée.</p>
        <UiChart
          v-else
          type="bar"
          title="Compétiteurs sélectionnés par saison"
          data-testid="chart-competitors"
          :labels="seasonLabels"
          :datasets="competitorDatasets"
        />
      </UiCard>
    </div>
  </div>
</template>
