<script setup lang="ts">
/* Outils › Import FFME (admins only): the MyFFME licensee list, matched to the members. */
import { inject } from "vue";
import { OUTILS_KEY } from "./context";
import FfmeImportPane from "./ffme/FfmeImportPane.vue";

const { toast } = inject(OUTILS_KEY)!;
</script>

<template>
  <section data-testid="pane-ffme-import">
    <FfmeImportPane @toast="toast.show" />
  </section>
</template>
