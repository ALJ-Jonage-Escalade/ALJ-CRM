<script setup lang="ts">
/* Administration (admins only): the layout of its sub-pages, starting with Accès (who may use the CRM). Online only:
   nothing of it is kept on the device. */
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";

const route = useRoute();
// The open sub-page (router.ts): its id, as AppShell lists it
const sub = computed(() => route.meta.sub ?? "acces");
</script>

<template>
  <AppShell page="administration" title="Administration" :sub="sub">
    <RouterView />
  </AppShell>
</template>
