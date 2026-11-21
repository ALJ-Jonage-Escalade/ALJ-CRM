<script setup lang="ts">
/* Outils › Export FFME: the licences CSV for the MyFFME import (linked from Adhérents). */
import { inject } from "vue";
import { OUTILS_KEY } from "./context";
import FfmeExportPane from "./ffme/FfmeExportPane.vue";

const { toast } = inject(OUTILS_KEY)!;
</script>

<template>
  <section data-testid="pane-ffme">
    <FfmeExportPane @toast="toast.show" />
  </section>
</template>
