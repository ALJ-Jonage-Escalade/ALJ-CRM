<script setup lang="ts">
/* Outils › Export FFME: the licences CSV for the MyFFME import (linked from Adhérents). */
import { inject, useTemplateRef } from "vue";
import { OUTILS_KEY, type ReloadablePage } from "./context";
import FfmeExportPane from "./FfmeExportPane.vue";

const { toast } = inject(OUTILS_KEY)!;
const pane = useTemplateRef<ReloadablePage>("pane");
defineExpose({ reload: () => pane.value?.reload() });
</script>

<template>
  <section data-testid="pane-ffme">
    <FfmeExportPane ref="pane" @toast="toast.show" />
  </section>
</template>
