<script setup lang="ts">
/* Outils › Statistiques: the competitions' figures. */
import { useTemplateRef } from "vue";
import type { ReloadablePage } from "./context";
import StatsPane from "./StatsPane.vue";

const pane = useTemplateRef<ReloadablePage>("pane");
defineExpose({ reload: () => pane.value?.reload() });
</script>

<template>
  <section data-testid="pane-stats">
    <StatsPane ref="pane" />
  </section>
</template>
