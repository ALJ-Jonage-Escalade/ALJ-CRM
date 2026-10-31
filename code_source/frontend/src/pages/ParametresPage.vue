<script setup lang="ts">
/* Paramètres (admins only): the layout of its sub-pages, Général (Google, server cache, results batch) and Campagne
   HelloAsso (the active campaigns). Online only: nothing of it is kept on the device. */
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";

const route = useRoute();
// The open sub-page (router.ts): its id, as AppShell lists it
const sub = computed(() => route.meta.sub ?? "general");
</script>

<template>
  <AppShell page="parametres" title="Paramètres" :sub="sub">
    <RouterView />
  </AppShell>
</template>
