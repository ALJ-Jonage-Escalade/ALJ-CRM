<script setup lang="ts">
/* Outils › Import HelloAsso (admins only): the registrations of the HelloAsso membership campaign, imported as members. */
import { useTemplateRef } from "vue";
import type { ReloadablePage } from "./context";
import HelloAssoImportPane from "./HelloAssoImportPane.vue";

const pane = useTemplateRef<ReloadablePage>("pane");
defineExpose({ reload: () => pane.value?.reload() });
</script>

<template>
  <section data-testid="pane-helloasso-import">
    <HelloAssoImportPane ref="pane" />
  </section>
</template>
