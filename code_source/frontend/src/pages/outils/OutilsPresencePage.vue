<script setup lang="ts">
/* Outils › Fiches de présence: attendance sheets (Excel A3) of the courses and of the autonomous members. */
import { inject } from "vue";
import { OUTILS_KEY } from "./context";
import PresencePane from "./presence/PresencePane.vue";

const { toast } = inject(OUTILS_KEY)!;
</script>

<template>
  <section data-testid="pane-presence">
    <PresencePane @toast="toast.show" />
  </section>
</template>
