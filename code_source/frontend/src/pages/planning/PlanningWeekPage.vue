<script setup lang="ts">
/* Planning › Vue semaine (the index sub-page): the slots on the week grid, a click on one opens it. */
import { inject } from "vue";
import { PLANNING_KEY } from "./context";
import WeekGrid from "./WeekGrid.vue";

const { slots, open } = inject(PLANNING_KEY)!;
</script>

<template>
  <WeekGrid :slots="slots" @open="open" />
</template>
