<script setup lang="ts">
/* Outils › Statistiques: the members' figures of a season, then the competitions' figures. */
import { useTemplateRef } from "vue";
import type { ReloadablePage } from "./context";
import MemberStatsPane from "./stats/MemberStatsPane.vue";
import StatsPane from "./stats/StatsPane.vue";

const members = useTemplateRef<ReloadablePage>("members");
const competitions = useTemplateRef<ReloadablePage>("competitions");
defineExpose({ reload: () => Promise.all([members.value?.reload(), competitions.value?.reload()]) });
</script>

<template>
  <section data-testid="pane-stats" class="flex flex-col gap-6">
    <div>
      <h2 class="text-sm font-black uppercase tracking-wide text-slate-700 mb-3">Adhérents</h2>
      <MemberStatsPane ref="members" />
    </div>
    <div>
      <h2 class="text-sm font-black uppercase tracking-wide text-slate-700 mb-3">Compétitions</h2>
      <StatsPane ref="competitions" />
    </div>
  </section>
</template>
