<script setup lang="ts">
/* Outils › Statistiques, competitions: competitions and competitors of the season, podiums of the last seasons, from the competitions on the server. */
import { computed, inject, onMounted, ref } from "vue";
import UiCard from "../../../components/ui/UiCard.vue";
import UiChart from "../../../components/ui/UiChart.vue";
import { HEX } from "../../../components/ui/palette";
import { ApiError, CLIENT_KEY, errorText } from "../../../lib/client";
import { createCompetitionsApi } from "../../../services/competitions";
import { formatEuros } from "../../../lib/format";
import { balances, totals } from "../../competitions/balance/balance";
import { seasonOf, todayIso, type Competition } from "../../competitions/competitions";
import { competitionsPerMonth, seasonParticipation, seasonPodiums } from "./stats";

/** Seasons whose podiums are added on the tile. */
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

const today = todayIso();
const currentSeason = seasonOf(today);
const participation = computed(() => seasonParticipation(competitions.value, today));
/** The « Total dû » of Compétitions › Bilan for the current season. */
const budget = computed(() => totals(balances(competitions.value, currentSeason, today)).due);
const seasons = computed(() => seasonPodiums(competitions.value, SEASON_COUNT));
const perMonth = computed(() => competitionsPerMonth(competitions.value, today));
const monthDatasets = computed(() => [
  { label: "Compétitions", data: perMonth.value.map((month) => month.competitions), colors: HEX.blue },
]);
const podiumCount = computed(() => seasons.value.reduce((sum, season) => sum + season.podiums, 0));
</script>

<template>
  <div class="flex flex-col gap-4" data-testid="stats-pane">
    <p v-if="loadError" data-testid="stats-load-error" role="alert" class="text-[13px] text-red-700">⚠️ {{ loadError }}</p>
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <UiCard class="text-center">
        <div class="text-2xl font-black text-sky-700" data-testid="kpi-competitions">{{ participation.competitions }}</div>
        <div class="text-xs font-semibold uppercase text-slate-500 mt-1">Compétitions {{ currentSeason }}</div>
      </UiCard>
      <UiCard class="text-center">
        <div class="text-2xl font-black text-indigo-700" data-testid="kpi-competitors">{{ participation.competitors }}</div>
        <div class="text-xs font-semibold uppercase text-slate-500 mt-1">Compétiteurs {{ currentSeason }}</div>
      </UiCard>
      <UiCard class="text-center">
        <div class="text-2xl font-black text-violet-700" data-testid="kpi-unique-competitors">{{ participation.uniqueCompetitors }}</div>
        <div class="text-xs font-semibold uppercase text-slate-500 mt-1">Compétiteurs uniques {{ currentSeason }}</div>
      </UiCard>
      <UiCard class="text-center">
        <div class="text-2xl font-black text-emerald-700" data-testid="kpi-budget">{{ formatEuros(budget) }}</div>
        <div class="text-xs font-semibold uppercase text-slate-500 mt-1">Budget total {{ currentSeason }}</div>
      </UiCard>
      <UiCard class="text-center">
        <div class="text-2xl font-black text-purple-700" data-testid="kpi-podiums">{{ seasons.length ? podiumCount : "—" }}</div>
        <div class="text-xs font-semibold uppercase text-slate-500 mt-1">Podiums ({{ seasons.length || SEASON_COUNT }} saisons)</div>
      </UiCard>
    </div>

    <UiCard>
      <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">📅 Compétitions par mois ({{ currentSeason }})</h3>
      <UiChart
        type="bar"
        title="Compétitions par mois de la saison"
        data-testid="chart-competitions-per-month"
        :labels="perMonth.map((month) => month.month)"
        :datasets="monthDatasets"
      />
    </UiCard>
  </div>
</template>
