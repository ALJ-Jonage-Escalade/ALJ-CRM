<script setup lang="ts">
/* Outils › Fiches de présence: attendance sheets (Excel A3) of the courses and of the autonomous members. */
import { inject, useTemplateRef } from "vue";
import { OUTILS_KEY, type ReloadablePage } from "./context";
import PresencePane from "./presence/PresencePane.vue";

const { toast } = inject(OUTILS_KEY)!;
const pane = useTemplateRef<ReloadablePage>("pane");
defineExpose({ reload: () => pane.value?.reload() });
</script>

<template>
  <section data-testid="pane-presence">
    <PresencePane ref="pane" @toast="toast.show" />
  </section>
</template>
