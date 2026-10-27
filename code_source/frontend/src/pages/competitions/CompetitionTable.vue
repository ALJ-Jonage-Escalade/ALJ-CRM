<script setup lang="ts">
import { RouterLink } from "vue-router";
import UiBadge from "../../components/ui/UiBadge.vue";
import UiButton from "../../components/ui/UiButton.vue";
import { formatDayText } from "../../lib/format";
import { plural } from "../../lib/text";
import { counts, discipline, disciplineColor, hasResults, type Competition } from "./competitions";

defineProps<{
  competitions: readonly Competition[];
  canWrite: boolean;
}>();

const emit = defineEmits<{
  edit: [competition: Competition];
  remove: [competition: Competition];
}>();
</script>

<template>
  <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="comp-table-container">
    <table class="w-full border-collapse text-left text-[13px]" data-testid="comp-table">
      <thead>
        <tr class="border-b border-slate-200 bg-slate-50 text-[11.5px] font-bold tracking-wide uppercase text-slate-500">
          <th class="px-3.5 py-2.5">Épreuve</th>
          <th class="px-3 py-2.5">Discipline</th>
          <th class="px-3 py-2.5">Date</th>
          <th class="px-3 py-2.5">Date de fin</th>
          <th class="px-3 py-2.5">Lieu</th>
          <th class="px-3 py-2.5 text-center">Participants</th>
          <th v-if="canWrite" class="px-3.5 py-2.5 text-right">Actions</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-100">
        <tr v-if="!competitions.length">
          <td :colspan="canWrite ? 7 : 6" class="px-4 py-8 text-center text-slate-500">Aucune compétition correspondante.</td>
        </tr>
        <tr v-for="c in competitions" :key="c.id" class="hover:bg-slate-50/80 transition-colors" data-testid="comp-table-row">
          <td class="px-3.5 py-2.5 font-medium text-slate-900">
            <RouterLink :to="{ query: { id: String(c.id) } }" class="font-semibold text-accent hover:underline flex items-center gap-1.5">
              <span v-if="hasResults(c)" title="Résultats officiels récupérés">🏆</span>
              {{ c.nom }}
            </RouterLink>
            <span v-if="c.id_ffme" class="block text-[11px] text-slate-400">N° FFME : {{ c.id_ffme }}</span>
          </td>
          <td class="px-3 py-2.5 whitespace-nowrap">
            <UiBadge v-if="discipline(c)" :color="disciplineColor(discipline(c))" variant="soft">
              {{ discipline(c) }}
            </UiBadge>
            <span v-else class="text-slate-400">—</span>
          </td>
          <td class="px-3 py-2.5 whitespace-nowrap font-medium text-slate-700">
            {{ c.date_competition ? formatDayText(c.date_competition) : "—" }}
          </td>
          <td class="px-3 py-2.5 whitespace-nowrap text-slate-600">
            {{ c.date_fin ? formatDayText(c.date_fin) : c.date_competition ? formatDayText(c.date_competition) : "—" }}
          </td>
          <td class="px-3 py-2.5 text-slate-600">
            {{ c.lieu || "—" }}
          </td>
          <td class="px-3 py-2.5 text-center whitespace-nowrap">
            <span class="inline-block rounded-full bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
              {{ counts(c.participants ?? []).selected }} participant{{ plural(counts(c.participants ?? []).selected) }}
            </span>
          </td>
          <td v-if="canWrite" class="px-3.5 py-2.5 text-right whitespace-nowrap">
            <div class="inline-flex items-center gap-1">
              <UiButton variant="muted" small data-testid="edit-comp-row" title="Modifier la compétition" @click="emit('edit', c)">
                ✏️
              </UiButton>
              <UiButton
                variant="muted"
                small
                danger
                data-testid="delete-comp-row"
                title="Supprimer la compétition"
                @click="emit('remove', c)"
              >
                🗑️
              </UiButton>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
