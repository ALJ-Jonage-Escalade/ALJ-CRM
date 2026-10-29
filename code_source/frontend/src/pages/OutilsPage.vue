<script setup lang="ts">
/* Outils (coaches and admins): members map, pivot table, competition statistics, attendance sheets, FFME CSV export
   and, for admins, import of the MyFFME licensee list. Layout of the sub-pages (router.ts, one per tool, linked from
   Adhérents for the FFME ones): loads the seasons they share and reloads the open one. A sub-page is loaded when first
   opened and kept while switching (route meta.keepAlive). Online only. */
import { computed, inject, onMounted, provide, ref } from "vue";
import { RouterView, useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiCard from "../components/ui/UiCard.vue";
import UiToast from "../components/ui/UiToast.vue";
import { useToast } from "../composables/toast";
import { CLIENT_KEY } from "../lib/client";
import { createMembersApi } from "../services/members";
import { OUTILS_KEY, type ReloadablePage } from "./outils/context";

const membersApi = createMembersApi(inject(CLIENT_KEY)!);
const route = useRoute();
const toast = useToast();

// The open sub-page (router.ts): its id, as AppShell lists it
const sub = computed(() => route.meta.sub ?? "map");

// Map and pivot table: the active season at first, or every season
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

// Reload of the open sub-page
const REFRESHED: Record<string, string> = {
  map: "🔄 Carte réactualisée.",
  pivot: "🔄 Tableau croisé dynamique réactualisé.",
  stats: "🔄 Statistiques des compétitions réactualisées.",
  presence: "🔄 Effectifs et créneaux réactualisés.",
  ffme: "🔄 Statistiques FFME réactualisées.",
  "ffme-import": "🔄 Formulaire d'import FFME réinitialisé.",
};
const openPage = ref<ReloadablePage | null>(null);

function refresh(): void {
  if (!openPage.value) {
    return;
  }
  void openPage.value.reload();
  toast.show(REFRESHED[sub.value] ?? "🔄 Outil réactualisé.");
}
</script>

<template>
  <AppShell page="outils" title="Outils" :sub="sub">
    <UiCard class="mb-3">
      <div class="flex flex-wrap items-center justify-between gap-2.5">
        <div class="min-w-0">
          <h2 class="text-base font-bold">🛠️ Outils d'analyse & exports</h2>
          <p class="text-xs text-slate-500">Cartographie, analyse des effectifs, fiches de présence (Excel A3) et licences FFME.</p>
        </div>
        <UiButton variant="muted" small data-testid="tools-refresh" title="Recharger l'outil actif" @click="refresh">🔄 Recharger</UiButton>
      </div>
    </UiCard>

    <RouterView v-slot="{ Component, route: shown }">
      <KeepAlive v-if="shown.meta.keepAlive">
        <component :is="Component" ref="openPage" />
      </KeepAlive>
      <component :is="Component" v-else ref="openPage" />
    </RouterView>

    <UiToast :message="toast.message.value" />
  </AppShell>
</template>
