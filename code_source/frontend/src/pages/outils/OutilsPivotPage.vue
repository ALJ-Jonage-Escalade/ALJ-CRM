<script setup lang="ts">
/* Outils › TCD: pivot table of the members, by season (vue-pivottable, in this sub-page's chunk). */
import { inject, ref, useTemplateRef, watch } from "vue";
import { OUTILS_KEY, type ReloadablePage } from "./context";
import PivotPane from "./PivotPane.vue";
import SeasonSelect from "./SeasonSelect.vue";

const { seasons, initialSeason } = inject(OUTILS_KEY)!;
const season = ref("");
watch(initialSeason, (initial) => (season.value ||= initial), { immediate: true });

const pivot = useTemplateRef<ReloadablePage>("pivot");
defineExpose({ reload: () => pivot.value?.reload() });
</script>

<template>
  <section data-testid="pane-pivot">
    <SeasonSelect v-model="season" :seasons="seasons" label="Saison à analyser :" testid="pivot-season" class="mb-2" />
    <PivotPane v-if="season" ref="pivot" :season="season" />
  </section>
</template>
