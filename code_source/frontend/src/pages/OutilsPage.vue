<script setup lang="ts">
/* Outils (coaches and admins): members map, member and competition statistics, attendance sheets, FFME CSV export
   and, for admins, imports of the MyFFME licensee list and of the HelloAsso membership campaign. Layout of the
   sub-pages (router.ts, one per tool, linked from Adhérents for the FFME ones): loads the seasons they share. A sub-page is loaded when first opened and kept while switching (route meta.keepAlive).
   Online only. */
import { computed, inject, onMounted, provide, ref } from "vue";
import { RouterView, useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";
import UiToast from "../components/ui/UiToast.vue";
import { useToast } from "../composables/toast";
import { CLIENT_KEY } from "../lib/client";
import { createMembersApi } from "../services/members";
import { OUTILS_KEY } from "./outils/context";

const membersApi = createMembersApi(inject(CLIENT_KEY)!);
const route = useRoute();
const toast = useToast();

// The open sub-page (router.ts): its id, as AppShell lists it
const sub = computed(() => route.meta.sub ?? "map");

// Map and statistics: the active season at first
const seasons = ref<string[]>([]);
const initialSeason = ref(""); // empty until the seasons are known

onMounted(async () => {
  let initial = "active"; // the server's active season
  try {
    const data = await membersApi.seasons();
    seasons.value = data.seasons;
    initial = data.seasons.includes(data.active) ? data.active : (data.seasons[0] ?? initial);
  } catch (e) {
    console.warn("Saisons des outils :", e);
  }
  initialSeason.value = initial;
});

provide(OUTILS_KEY, { seasons, initialSeason, toast });
</script>

<template>
  <AppShell page="outils" title="Outils" :sub="sub">
    <RouterView v-slot="{ Component, route: shown }">
      <KeepAlive v-if="shown.meta.keepAlive">
        <component :is="Component" />
      </KeepAlive>
      <component :is="Component" v-else />
    </RouterView>

    <UiToast :message="toast.message.value" />
  </AppShell>
</template>
