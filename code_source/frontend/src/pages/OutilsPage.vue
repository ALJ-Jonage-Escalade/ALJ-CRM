<script setup lang="ts">
/* Outils (coaches and admins): members map, pivot table (vue-pivottable, loaded with its tab), attendance sheets,
   FFME CSV export and, for admins, import of the MyFFME licensee list. The open tab is in the URL (?tab=ffme, linked
   from Adhérents). A tab is loaded when first opened and kept while switching. Online only. */
import { computed, defineAsyncComponent, inject, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppShell from "../components/AppShell.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiCard from "../components/ui/UiCard.vue";
import UiToast from "../components/ui/UiToast.vue";
import { AUTH_KEY } from "../composables/auth";
import { useToast } from "../composables/toast";
import { CLIENT_KEY } from "../lib/client";
import { createMembersApi } from "../services/members";
import FfmeExportPane from "./outils/FfmeExportPane.vue";
import FfmeImportPane from "./outils/FfmeImportPane.vue";
import MembersMap from "./outils/MembersMap.vue";
import PresencePane from "./outils/PresencePane.vue";
import SeasonSelect from "./outils/SeasonSelect.vue";
import StatsPane from "./outils/StatsPane.vue";

// The pivot table library is downloaded on the first opening of its tab
const PivotPane = defineAsyncComponent(() => import("./outils/PivotPane.vue"));

const membersApi = createMembersApi(inject(CLIENT_KEY)!);
const auth = inject(AUTH_KEY)!;
const route = useRoute();
const router = useRouter();
const toast = useToast();

const TABS = [
  { id: "map", label: "📍 Carte géographique", refreshed: "🔄 Carte réactualisée." },
  { id: "pivot", label: "📊 Analyse des effectifs (TCD)", refreshed: "🔄 Tableau croisé dynamique réactualisé." },
  { id: "stats", label: "📈 Statistiques compétitions", refreshed: "🔄 Statistiques des compétitions réactualisées." },
  { id: "presence", label: "📋 Fiches de présence", refreshed: "🔄 Effectifs et créneaux réactualisés." },
  { id: "ffme", label: "🇫🇷 Export CSV FFME", refreshed: "🔄 Statistiques FFME réactualisées." },
  { id: "ffme-import", label: "📥 Import Excel FFME", refreshed: "🔄 Formulaire d'import FFME réinitialisé.", admin: true },
] as const;
type TabId = (typeof TABS)[number]["id"];

const isAdmin = computed(() => auth.state.value.status === "signedIn" && auth.state.value.role === "admin");
const tabs = computed(() => TABS.filter((t) => !("admin" in t) || isAdmin.value));
const tab = computed<TabId>(() => tabs.value.find((t) => t.id === route.query.tab)?.id ?? "map");
// Tabs opened once stay mounted (loaded frames and typed values are kept)
const opened = reactive(new Set<TabId>());
const isOpen = (id: TabId) => tab.value === id || opened.has(id);

function show(id: TabId): void {
  opened.add(tab.value);
  void router.replace({ query: { ...route.query, tab: id === "map" ? undefined : id } });
}

// Map and pivot table: the active season at first, or every season
const seasons = ref<string[]>([]);
const mapSeason = ref(""); // empty until the seasons are known
const pivotSeason = ref("");

onMounted(async () => {
  let initial = "active"; // the server's active season
  try {
    const data = await membersApi.seasons();
    seasons.value = data.seasons;
    initial = data.seasons.includes(data.active) ? data.active : (data.seasons[0] ?? initial);
  } catch (e) {
    console.warn("Saisons des outils :", e);
  }
  mapSeason.value = initial;
  pivotSeason.value = initial;
});

// Reload of the open tab
const panes: Partial<Record<TabId, { reload(): unknown }>> = {};
const keep = (id: TabId) => (pane: unknown) => {
  if (pane) {
    panes[id] = pane as { reload(): unknown };
  } else {
    delete panes[id];
  }
};

function refresh(): void {
  const pane = panes[tab.value];
  if (!pane) {
    return;
  }
  void pane.reload();
  toast.show(TABS.find((t) => t.id === tab.value)!.refreshed);
}

const chip = (active: boolean) => [
  "cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold",
  active ? "border-accent bg-accent text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
];
</script>

<template>
  <AppShell page="outils" title="Outils">
    <UiCard class="mb-3">
      <div class="flex flex-wrap items-center justify-between gap-2.5">
        <div class="min-w-0">
          <h2 class="text-base font-bold">🛠️ Outils d'analyse & exports</h2>
          <p class="text-xs text-slate-500">Cartographie, analyse des effectifs, fiches de présence (Excel A3) et licences FFME.</p>
        </div>
        <UiButton variant="muted" small data-testid="tools-refresh" title="Recharger l'outil actif" @click="refresh">🔄 Recharger</UiButton>
      </div>
      <div class="mt-2.5 flex flex-wrap gap-1.5 border-t border-slate-100 pt-2">
        <button
          v-for="t in tabs"
          :key="t.id"
          type="button"
          :data-testid="`tab-${t.id}`"
          :aria-pressed="tab === t.id"
          :class="chip(tab === t.id)"
          @click="show(t.id)"
        >
          {{ t.label }}
        </button>
      </div>
    </UiCard>

    <section v-if="isOpen('map')" v-show="tab === 'map'" data-testid="pane-map">
      <SeasonSelect v-model="mapSeason" :seasons="seasons" label="Saison à afficher :" testid="map-season" class="mb-2" />
      <MembersMap v-if="mapSeason" :ref="keep('map')" :season="mapSeason" />
    </section>

    <section v-if="isOpen('pivot')" v-show="tab === 'pivot'" data-testid="pane-pivot">
      <SeasonSelect v-model="pivotSeason" :seasons="seasons" label="Saison à analyser :" testid="pivot-season" class="mb-2" />
      <PivotPane v-if="pivotSeason" :ref="keep('pivot')" :season="pivotSeason" />
    </section>

    <section v-if="isOpen('stats')" v-show="tab === 'stats'" data-testid="pane-stats">
      <StatsPane :ref="keep('stats')" />
    </section>

    <section v-if="isOpen('presence')" v-show="tab === 'presence'" data-testid="pane-presence">
      <PresencePane :ref="keep('presence')" @toast="toast.show" />
    </section>

    <section v-if="isOpen('ffme')" v-show="tab === 'ffme'" data-testid="pane-ffme">
      <FfmeExportPane :ref="keep('ffme')" @toast="toast.show" />
    </section>

    <section v-if="isAdmin && isOpen('ffme-import')" v-show="tab === 'ffme-import'" data-testid="pane-ffme-import">
      <FfmeImportPane :ref="keep('ffme-import')" @toast="toast.show" />
    </section>

    <UiToast :message="toast.message.value" />
  </AppShell>
</template>
