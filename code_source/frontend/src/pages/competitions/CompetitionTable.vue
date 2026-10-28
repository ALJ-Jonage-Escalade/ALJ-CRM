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
  // A competition opened (also when it is already the selected one: the URL does not change then)
  open: [competition: Competition];
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
        <tr
          v-for="competition in competitions"
          :key="competition.id"
          class="hover:bg-slate-50/80 transition-colors"
          data-testid="comp-table-row"
        >
          <td class="px-3.5 py-2.5 font-medium text-slate-900">
            <RouterLink
              :to="{ query: { id: String(competition.id) } }"
              data-testid="comp-table-open"
              class="font-semibold text-accent hover:underline flex items-center gap-1.5"
              @click="emit('open', competition)"
            >
              <span v-if="hasResults(competition)" title="Résultats officiels récupérés">🏆</span>
              {{ competition.nom }}
            </RouterLink>
            <span v-if="competition.id_ffme" class="block text-[11px] text-slate-400">N° FFME : {{ competition.id_ffme }}</span>
          </td>
          <td class="px-3 py-2.5 whitespace-nowrap">
            <UiBadge v-if="discipline(competition)" :color="disciplineColor(discipline(competition))" variant="soft">
              {{ discipline(competition) }}
            </UiBadge>
            <span v-else class="text-slate-400">—</span>
          </td>
          <td class="px-3 py-2.5 whitespace-nowrap font-medium text-slate-700">
            {{ competition.date_competition ? formatDayText(competition.date_competition) : "—" }}
          </td>
          <td class="px-3 py-2.5 whitespace-nowrap text-slate-600">
            {{
              competition.date_fin
                ? formatDayText(competition.date_fin)
                : competition.date_competition
                  ? formatDayText(competition.date_competition)
                  : "—"
            }}
          </td>
          <td class="px-3 py-2.5 text-slate-600">
            {{ competition.lieu || "—" }}
          </td>
          <td class="px-3 py-2.5 text-center whitespace-nowrap">
            <span class="inline-block rounded-full bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
              {{ counts(competition.participants ?? []).selected }} participant{{ plural(counts(competition.participants ?? []).selected) }}
            </span>
          </td>
          <td v-if="canWrite" class="px-3.5 py-2.5 text-right whitespace-nowrap">
            <div class="inline-flex items-center gap-1">
              <UiButton
                variant="muted"
                small
                data-testid="edit-comp-row"
                title="Modifier la compétition"
                @click="emit('edit', competition)"
              >
                ✏️
              </UiButton>
              <UiButton
                variant="muted"
                small
                danger
                data-testid="delete-comp-row"
                title="Supprimer la compétition"
                @click="emit('remove', competition)"
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
