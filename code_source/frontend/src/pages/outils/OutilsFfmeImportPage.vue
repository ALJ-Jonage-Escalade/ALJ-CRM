<script setup lang="ts">
/* Outils › Import FFME (admins only): the MyFFME licensee list, matched to the members. */
import { inject, useTemplateRef } from "vue";
import { OUTILS_KEY, type ReloadablePage } from "./context";
import FfmeImportPane from "./FfmeImportPane.vue";

const { toast } = inject(OUTILS_KEY)!;
const pane = useTemplateRef<ReloadablePage>("pane");
defineExpose({ reload: () => pane.value?.reload() });
</script>

<template>
  <section data-testid="pane-ffme-import">
    <FfmeImportPane ref="pane" @toast="toast.show" />
  </section>
</template>
