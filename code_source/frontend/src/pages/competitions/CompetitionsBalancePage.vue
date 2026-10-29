<script setup lang="ts">
/* Compétitions › Bilan (coaches and admins, offline too on a coach's device): the season's figures. */
import { inject } from "vue";
import BalancePane from "./balance/BalancePane.vue";
import { COMPETITIONS_KEY } from "./context";

const { all, listPath } = inject(COMPETITIONS_KEY)!;
</script>

<template>
  <BalancePane :competitions="all" :list-path="listPath" />
</template>
