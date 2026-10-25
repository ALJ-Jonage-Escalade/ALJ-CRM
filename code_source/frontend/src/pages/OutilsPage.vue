<script setup lang="ts">
/* Outils (coaches and admins): members map and pivot table (pages of the server in sandboxed frames), attendance
   sheets, FFME CSV export and, for admins, import of the MyFFME licensee list. The open tab is in the URL (?tab=ffme,
   linked from Adhérents). A tab is loaded when first opened and kept while switching. Online only. */
import { computed, inject, onMounted, reactive, ref } from "vue";
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
import PresencePane from "./outils/PresencePane.vue";
import ToolFrame from "./outils/ToolFrame.vue";

const membersApi = createMembersApi(inject(CLIENT_KEY)!);
const auth = inject(AUTH_KEY)!;
const route = useRoute();
const router = useRouter();
const toast = useToast();

const TABS = [
  { id: "map", label: "📍 Carte géographique", refreshed: "🔄 Carte réactualisée." },
  { id: "pivot", label: "📊 Analyse des effectifs (TCD)", refreshed: "🔄 Tableau croisé dynamique réactualisé." },
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

// Pivot table: the active season, or every season
const ALL_SEASONS = "Toutes les saisons";
const seasons = ref<string[]>([]);
const season = ref(""); // empty until the seasons are known
const pivotUrl = computed(() => `/pivot?season=${encodeURIComponent(season.value)}`);

onMounted(async () => {
  try {
    const data = await membersApi.seasons();
    seasons.value = data.seasons;
    season.value = data.seasons.includes(data.active) ? data.active : (data.seasons[0] ?? "active");
  } catch (e) {
    console.warn("Saisons des outils :", e);
    season.value = "active"; // the server's active season
  }
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
      <ToolFrame
        :ref="keep('map')"
        url="/map"
        sandbox="allow-scripts allow-popups"
        title="Carte Leaflet des adhérents"
        loading="Chargement de la carte géographique des adhérents…"
        testid="map-frame"
      />
    </section>

    <section v-if="isOpen('pivot')" v-show="tab === 'pivot'" data-testid="pane-pivot">
      <label class="mb-2 flex items-center gap-2 text-[12.5px] font-semibold text-slate-500">
        Saison à analyser :
        <select
          v-model="season"
          data-testid="pivot-season"
          class="rounded-md border border-slate-300 bg-white px-2 py-1 text-[12.5px] text-slate-800"
        >
          <option v-for="s in seasons" :key="s" :value="s">{{ s }}</option>
          <option :value="ALL_SEASONS">{{ ALL_SEASONS }}</option>
        </select>
      </label>
      <ToolFrame
        v-if="season"
        :ref="keep('pivot')"
        :url="pivotUrl"
        sandbox="allow-scripts allow-popups allow-modals"
        title="Tableau Croisé Dynamique"
        loading="Chargement du tableau croisé dynamique…"
        testid="pivot-frame"
      />
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
