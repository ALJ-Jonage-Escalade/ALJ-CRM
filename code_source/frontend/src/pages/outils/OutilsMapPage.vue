<script setup lang="ts">
/* Outils › Carte (index sub-page): the members' addresses on a map, by season. */
import { inject, ref, watch } from "vue";
import { OUTILS_KEY } from "./context";
import MembersMap from "./map/MembersMap.vue";
import SeasonSelect from "./SeasonSelect.vue";

const { seasons, initialSeason } = inject(OUTILS_KEY)!;
const season = ref("");
watch(initialSeason, (initial) => (season.value ||= initial), { immediate: true });
</script>

<template>
  <section data-testid="pane-map">
    <SeasonSelect v-model="season" :seasons="seasons" label="Saison à afficher :" testid="map-season" class="mb-2" />
    <MembersMap v-if="season" :season="season" />
  </section>
</template>
