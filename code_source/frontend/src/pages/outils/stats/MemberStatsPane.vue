<script setup lang="ts">
/* Outils › Statistiques, members: charts of the season picked, counted in the browser from every season's rows
   (one request, the season change filters locally). Online only: nothing is kept on the device. */
import { computed, inject, onMounted, ref, watch } from "vue";
import UiCard from "../../../components/ui/UiCard.vue";
import UiChart from "../../../components/ui/UiChart.vue";
import { ApiError, CLIENT_KEY, errorText } from "../../../lib/client";
import { createReportsApi } from "../../../services/reports";
import { OUTILS_KEY } from "../context";
import SeasonSelect from "../SeasonSelect.vue";
import { CATEGORY_COLORS, countBy, seasonMembers, type MemberStatsRecord } from "./memberStats";

const reportsApi = createReportsApi(inject(CLIENT_KEY)!);
const { seasons, initialSeason } = inject(OUTILS_KEY)!;
const season = ref("");
watch(initialSeason, (initial) => (season.value ||= initial), { immediate: true });

const records = ref<MemberStatsRecord[] | null>(null);
const offline = ref(false);
const loadError = ref("");

async function load(): Promise<void> {
  loadError.value = "";
  offline.value = false;
  try {
    records.value = (await reportsApi.memberStats()).records;
  } catch (e) {
    records.value = null;
    offline.value = e instanceof ApiError && e.status === 0;
    loadError.value = offline.value ? "" : errorText(e);
  }
}

onMounted(load);
defineExpose({ reload: load });

const members = computed(() => seasonMembers(records.value ?? [], season.value));
const sexSlices = computed(() => countBy(members.value, "sex"));
</script>

<template>
  <div class="flex flex-col gap-4" data-testid="member-stats">
    <SeasonSelect v-model="season" :seasons="seasons" :all-seasons="false" label="Saison :" testid="stats-season" />
    <p v-if="offline" data-testid="member-stats-offline" class="text-[13px] italic text-slate-500">
      Statistiques indisponibles hors ligne.
    </p>
    <p v-else-if="loadError" data-testid="member-stats-error" role="alert" class="text-[13px] text-red-700">⚠️ {{ loadError }}</p>
    <div v-else-if="records" class="grid gap-4 md:grid-cols-2">
      <UiCard>
        <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">Sexe</h3>
        <UiChart
          type="pie"
          title="Adhérents par sexe"
          data-testid="chart-sex"
          :labels="sexSlices.map((slice) => slice.label)"
          :datasets="[
            {
              label: 'Adhérents',
              data: sexSlices.map((slice) => slice.count),
              colors: sexSlices.map((slice) => CATEGORY_COLORS[slice.label] ?? '#94a3b8'),
            },
          ]"
        />
      </UiCard>
    </div>
  </div>
</template>
