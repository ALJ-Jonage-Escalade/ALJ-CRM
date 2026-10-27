<script setup lang="ts">
import { computed } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import { formatDayText } from "../../lib/format";
import { ranking, type Competition, type Row } from "./competitions";

const props = defineProps<{
  competition: Competition;
  rows: readonly Row[];
  canWrite: boolean;
  fetching: boolean;
}>();

const emit = defineEmits<{
  fetchResults: [];
}>();

const rankedRows = computed(() =>
  props.rows
    .filter((r) => r.classement || r.resultat_ffme)
    .slice()
    .sort((a, b) => {
      const rankA = parseInt(String(a.classement || "9999"), 10) || 9999;
      const rankB = parseInt(String(b.classement || "9999"), 10) || 9999;
      return rankA - rankB;
    }),
);

function medal(rank?: number | string | null): string {
  const n = parseInt(String(rank || ""), 10);
  if (n === 1) {
    return "🥇";
  }
  if (n === 2) {
    return "🥈";
  }
  if (n === 3) {
    return "🥉";
  }
  return "";
}
</script>

<template>
  <div class="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="results-section">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
      <div>
        <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5">🏆 Résultats MyCompet</h3>
        <p class="text-xs text-slate-500">
          <template v-if="competition.resultats_synced_at">
            Dernière synchronisation : {{ formatDayText(competition.resultats_synced_at) }}
          </template>
          <template v-else>Aucun résultat synchronisé pour le moment.</template>
        </p>
      </div>
      <div v-if="canWrite" class="flex items-center gap-2">
        <UiButton
          variant="muted"
          small
          :busy="fetching && 'Recherche en cours…'"
          data-testid="sync-results-btn"
          @click="emit('fetchResults')"
        >
          🔄 Actualiser les résultats
        </UiButton>
      </div>
    </div>

    <!-- Si aucun résultat -->
    <div v-if="!rankedRows.length" class="text-xs text-slate-500 italic py-3 text-center">
      Aucun résultat officiel FFME n'est encore enregistré pour les compétiteurs de cette épreuve.
    </div>

    <!-- Liste / Tableau des résultats -->
    <div v-else class="overflow-x-auto">
      <table class="w-full border-collapse text-left text-xs" data-testid="results-table">
        <thead>
          <tr class="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase text-slate-500">
            <th class="px-3 py-2 text-center w-16">Rang</th>
            <th class="px-3 py-2">Athlète</th>
            <th class="px-3 py-2">Catégorie</th>
            <th class="px-3 py-2">Performance / Score</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr
            v-for="r in rankedRows"
            :key="r.adherent_id ?? r.nom"
            :class="['hover:bg-slate-50 transition-colors', r.classement === '1' ? 'bg-amber-50/40 font-bold' : '']"
          >
            <td class="px-3 py-2 text-center font-bold text-slate-800 whitespace-nowrap">
              <span class="mr-1">{{ medal(r.classement) }}</span>
              {{ r.classement || "—" }}
            </td>
            <td class="px-3 py-2 font-medium text-slate-900">{{ r.nom }} {{ r.prenom }}</td>
            <td class="px-3 py-2 text-slate-600">
              {{ r.categorie_ffme || "—" }}
            </td>
            <td class="px-3 py-2 font-semibold text-blue-700">
              {{ ranking(r) || r.resultat_ffme || "Classé" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
