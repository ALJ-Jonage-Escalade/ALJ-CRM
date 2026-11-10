<script setup lang="ts">
/* One competition of the cards view: a link opening its detail. */
import { computed } from "vue";
import { RouterLink } from "vue-router";
import UiBadge from "../../../components/ui/UiBadge.vue";
import { plural } from "../../../lib/text";
import { counts, shownDiscipline, disciplineColor, periodText, hasResults, type Competition } from "../competitions";

const props = defineProps<{
  competition: Competition;
  selected: boolean;
}>();

const count = computed(() => counts(props.competition.participants ?? []));
</script>

<template>
  <RouterLink
    :to="{ query: { id: String(competition.id) } }"
    data-testid="comp-card"
    :aria-current="selected ? 'true' : undefined"
    :class="[
      'block rounded-xl border bg-white px-3.5 py-3 text-slate-800 no-underline shadow-sm hover:border-accent',
      selected ? 'border-accent' : 'border-slate-200',
    ]"
  >
    <div class="flex items-start justify-between gap-2 pb-1">
      <b class="block text-[15px]" data-testid="comp-name">
        <span v-if="hasResults(competition)" title="Résultats officiels récupérés">🏆</span>
        {{ competition.nom }}
      </b>
      <UiBadge
        v-if="shownDiscipline(competition)"
        :color="disciplineColor(shownDiscipline(competition))"
        variant="soft"
        class="ml-1 shrink-0"
        data-testid="discipline"
      >
        {{ shownDiscipline(competition) }}
      </UiBadge>
    </div>
    <span class="block text-xs font-semibold text-slate-600 pb-1.5" data-testid="comp-period">📅 {{ periodText(competition) }}</span>
    <span class="block text-xs text-slate-500">
      🏃 {{ competition.coaches?.length ? `Coachs : ${competition.coaches.join(", ")}` : "Aucun coach" }}
    </span>
    <span class="mt-0.5 block text-xs font-semibold text-blue-900">
      ({{ count.selected }} participant{{ plural(count.selected) }} · {{ count.unpaid }} en attente · {{ count.paid }} payé{{
        plural(count.paid)
      }})
    </span>
  </RouterLink>
</template>
