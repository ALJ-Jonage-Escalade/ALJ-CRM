<script setup lang="ts">
/* Outils › Statistiques: presence, podiums and competitors of the last seasons, from the competitions on the server. */
import { computed, inject, onMounted, ref } from "vue";
import UiCard from "../../../components/ui/UiCard.vue";
import { ApiError, CLIENT_KEY, errorText } from "../../../lib/client";
import { plural } from "../../../lib/text";
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

defineExpose({ reload: load });

const seasons = computed(() => seasonStats(competitions.value, SEASON_COUNT));
const participationRate = computed(() => participationRateText(competitions.value));
const podiumCount = computed(() => seasons.value.reduce((sum, season) => sum + season.podiums, 0));
const competitorGrowth = computed(() => competitorGrowthText(seasons.value));
/** The bars of the competitors list, relative to the busiest season. */
const mostCompetitors = computed(() => Math.max(1, ...seasons.value.map((season) => season.competitors)));
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
        <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">🏆 Nombre de podiums par saison</h3>
        <p v-if="!seasons.length" class="text-xs italic text-slate-400">Aucune compétition datée.</p>
        <div class="flex flex-col gap-3 text-xs">
          <div
            v-for="season in seasons"
            :key="season.season"
            class="rounded-lg border border-slate-100 bg-slate-50 p-2.5"
            data-testid="stats-podiums"
          >
            <div class="flex items-center justify-between font-bold text-slate-800 mb-1">
              <span>Saison {{ season.season }}</span>
              <span class="text-amber-700 text-sm font-black">{{ season.podiums }} podium{{ plural(season.podiums) }}</span>
            </div>
            <div class="text-slate-600 font-medium">🥇 {{ season.gold }} 🥈 {{ season.silver }} 🥉 {{ season.bronze }}</div>
          </div>
        </div>
      </UiCard>

      <UiCard>
        <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">📈 Compétiteurs sélectionnés par saison</h3>
        <p v-if="!seasons.length" class="text-xs italic text-slate-400">Aucune compétition datée.</p>
        <div class="flex flex-col gap-3 text-xs">
          <div v-for="season in seasons" :key="season.season" data-testid="stats-competitors">
            <div class="flex justify-between font-bold text-slate-800 mb-1">
              <span>Saison {{ season.season }}</span>
              <span>{{ season.competitors }} compétiteur{{ plural(season.competitors) }}</span>
            </div>
            <div class="h-3 w-full rounded-full bg-slate-100 overflow-hidden">
              <div
                class="h-full rounded-full bg-blue-600 transition-all duration-300"
                :style="{ width: `${(season.competitors / mostCompetitors) * 100}%` }"
              />
            </div>
          </div>
        </div>
      </UiCard>
    </div>
  </div>
</template>
