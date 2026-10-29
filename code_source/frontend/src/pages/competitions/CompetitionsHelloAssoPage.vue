<script setup lang="ts">
/* Compétitions › HelloAsso (coaches and admins, online only): the HelloAsso payments to link to the participants. */
import { inject } from "vue";
import { COMPETITIONS_KEY } from "./context";
import HelloAssoPane from "./helloasso/HelloAssoPane.vue";

const { items, all, members, listPath } = inject(COMPETITIONS_KEY)!;
</script>

<template>
  <HelloAssoPane
    :items="items.data.value"
    :loading="items.state.value === 'loading'"
    :competitions="all"
    :members="members.data.value ?? []"
    :list-path="listPath"
    @changed="items.refresh()"
  />
</template>
