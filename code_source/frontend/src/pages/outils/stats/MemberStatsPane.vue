<script setup lang="ts">
/* Outils › Statistiques, members: charts of the season picked, counted in the browser from every season's rows
   (one request, the season change filters locally). Online only: nothing is kept on the device. */
import { computed, inject, onMounted, ref, watch } from "vue";
import UiCard from "../../../components/ui/UiCard.vue";
import UiChart from "../../../components/ui/UiChart.vue";
import { HEX } from "../../../components/ui/palette";
import MemberChartCard from "./MemberChartCard.vue";
import { ApiError, CLIENT_KEY, errorText } from "../../../lib/client";
import { createReportsApi } from "../../../services/reports";
import { OUTILS_KEY } from "../context";
import SeasonSelect from "../SeasonSelect.vue";
import { CATEGORY_COLORS, memberCards, membersPerSeason, seasonMembers, type MemberStatsRecord } from "./memberStats";

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

const members = computed(() => seasonMembers(records.value ?? [], season.value));
const cards = computed(() => memberCards(members.value, records.value ?? [], season.value));
const perSeason = computed(() => membersPerSeason(records.value ?? []));
/** Groups add up to more than the members when someone paid for several. */
const groupsNote = computed(() =>
  members.value.some((member) => member.groups.length > 1) ? "Un adhérent inscrit dans plusieurs groupes compte dans chacun." : "",
);
/** A line per sex, and the total dashed. */
const perSeasonDatasets = computed(() => [
  ...perSeason.value.series.map((serie) => ({ label: serie.label, data: serie.values, colors: CATEGORY_COLORS[serie.label] ?? HEX.slate })),
  {
    label: "Total",
    data: perSeason.value.labels.map((_, index) => perSeason.value.series.reduce((sum, serie) => sum + (serie.values[index] ?? 0), 0)),
    colors: HEX.blue,
    dashed: true,
  },
]);
const percentText = (value: number | null) => (value === null ? "—" : `${value} %`);
</script>

<template>
  <div class="flex flex-col gap-4" data-testid="member-stats">
    <SeasonSelect v-model="season" :seasons="seasons" :all-seasons="false" label="Saison :" testid="stats-season" />
    <p v-if="offline" data-testid="member-stats-offline" class="text-[13px] italic text-slate-500">
      Statistiques indisponibles hors ligne.
    </p>
    <p v-else-if="loadError" data-testid="member-stats-error" role="alert" class="text-[13px] text-red-700">⚠️ {{ loadError }}</p>
    <template v-else-if="records">
      <div class="grid gap-3 grid-cols-2 sm:grid-cols-4">
        <UiCard
          v-for="card in [
            { id: 'members', label: 'Adhérents', value: String(cards.members) },
            { id: 'new', label: 'Nouveaux', value: percentText(cards.newPercent) },
            { id: 'age', label: 'Âge moyen', value: cards.averageAge === null ? '—' : `${cards.averageAge} ans` },
            { id: 'cancelled', label: 'Inscriptions annulées', value: String(cards.cancelled) },
          ]"
          :key="card.id"
          class="text-center"
          :data-testid="`card-${card.id}`"
        >
          <div class="text-2xl font-black text-blue-700">{{ card.value }}</div>
          <div class="text-xs font-semibold uppercase text-slate-500 mt-1">{{ card.label }}</div>
        </UiCard>
      </div>
      <div class="grid gap-4 md:grid-cols-2">
        <MemberChartCard
          id="sex"
          title="Sexe"
          type="pie"
          dimension="sex"
          :members="members"
          :detail="{ series: 'sex', bars: 'group', title: 'Sexe par groupe' }"
        />
        <MemberChartCard
          id="returning"
          title="Nouveaux / renouvellements"
          type="pie"
          dimension="returning"
          :members="members"
          :detail="{ series: 'returning', bars: 'group', title: 'Nouveaux / renouvellements par groupe' }"
        />
        <MemberChartCard
          id="age"
          title="Tranches d'âge"
          type="bar"
          dimension="ageBand"
          :members="members"
          :detail="{ series: 'sex', bars: 'ageBand', title: 'Sexe par tranche d\'âge' }"
        />
        <MemberChartCard
          id="group"
          title="Groupes"
          type="bar"
          horizontal
          dimension="group"
          :members="members"
          :note="groupsNote"
          :detail="{ series: 'sex', bars: 'group', title: 'Sexe par groupe' }"
        />
        <MemberChartCard
          id="city"
          title="Villes"
          type="bar"
          horizontal
          dimension="city"
          :members="members"
          :detail="{ series: 'sex', bars: 'city', title: 'Sexe par ville' }"
        />
        <MemberChartCard
          id="month"
          title="Inscriptions par mois"
          type="bar"
          dimension="orderMonth"
          :members="members"
          :detail="{ series: 'returning', bars: 'orderMonth', title: 'Nouveaux / renouvellements par mois' }"
        />
      </div>
      <UiCard>
        <h3 class="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">Adhérents par saison</h3>
        <UiChart
          type="line"
          title="Adhérents par saison et par sexe"
          data-testid="chart-seasons"
          :labels="perSeason.labels"
          :datasets="perSeasonDatasets"
        />
      </UiCard>
    </template>
  </div>
</template>
