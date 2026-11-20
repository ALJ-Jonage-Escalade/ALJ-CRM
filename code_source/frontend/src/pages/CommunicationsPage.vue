<script setup lang="ts">
/* Communications (admins only): the layout of its sub-pages, Modèles (e-mail templates, WhatsApp text) and Historique
   des envois (the e-mail log of the whole app). Online only: nothing of it is kept on the device. */
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";

const route = useRoute();
// The open sub-page (router.ts): its id, as AppShell lists it
const sub = computed(() => route.meta.sub ?? "modeles");
</script>

<template>
  <AppShell page="communications" title="Communications" :sub="sub">
    <RouterView />
  </AppShell>
</template>
