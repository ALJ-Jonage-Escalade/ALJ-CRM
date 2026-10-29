<script setup lang="ts">
/* Compétitions › Coachs (coaches and admins, offline too on a coach's device): the coaches and their competitions. */
import { inject } from "vue";
import CoachesPane from "./CoachesPane.vue";
import { COMPETITIONS_KEY } from "./context";

const { coaches, competitions, all, listPath } = inject(COMPETITIONS_KEY)!;
</script>

<template>
  <CoachesPane :coaches="coaches.data.value" :competitions="all" :list-path="listPath" @changed="competitions.refresh()" />
</template>
