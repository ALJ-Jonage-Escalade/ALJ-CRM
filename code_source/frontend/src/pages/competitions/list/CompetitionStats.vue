<script setup lang="ts">
/* The statistics tiles shown when no competition is opened. */
import { computed } from "vue";
import { formatEuros } from "../../../lib/format";
import { plural } from "../../../lib/text";
import type { Competition } from "../competitions";
import { competitionStats } from "./stats";

const props = defineProps<{
  competitions: readonly Competition[];
  today: string;
}>();

const stats = computed(() => competitionStats(props.competitions, props.today));
</script>

<template>
  <div class="grid grid-cols-1 gap-2.5 sm:grid-cols-3" data-testid="competitions-stats-tiles">
    <div class="rounded-xl border border-slate-200 bg-white p-4 text-center shadow-sm" data-testid="tile-total-competitions">
      <div class="text-2xl font-black text-blue-700" data-testid="stats-total-competitions">
        {{ stats.competitions }}
      </div>
      <div class="mt-1 text-xs font-semibold uppercase text-slate-500">Compétitions au total</div>
      <div class="mt-1 text-[11px] text-slate-400">{{ stats.upcoming }} à venir · {{ stats.past }} passée{{ plural(stats.past) }}</div>
    </div>
    <div class="rounded-xl border border-slate-200 bg-white p-4 text-center shadow-sm" data-testid="tile-total-competitors">
      <div class="text-2xl font-black text-emerald-700" data-testid="stats-total-competitors">
        {{ stats.competitors }}
      </div>
      <div class="mt-1 text-xs font-semibold uppercase text-slate-500">Compétiteurs</div>
      <div class="mt-1 text-[11px] text-slate-400">
        {{ stats.participations }} inscription{{ plural(stats.participations) }} cumulée{{ plural(stats.participations) }}
      </div>
    </div>
    <div class="rounded-xl border border-slate-200 bg-white p-4 text-center shadow-sm" data-testid="tile-total-budget">
      <div class="text-2xl font-black text-indigo-700" data-testid="stats-total-budget">
        {{ formatEuros(stats.budget) }}
      </div>
      <div class="mt-1 text-xs font-semibold uppercase text-slate-500">Budget total</div>
      <div class="mt-1 text-[11px] text-slate-400">{{ formatEuros(stats.paid) }} déjà réglé{{ plural(Math.round(stats.paid)) }}</div>
    </div>
  </div>
</template>
