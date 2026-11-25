<script setup lang="ts">
import { computed, inject, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";
import UiBadge from "../components/ui/UiBadge.vue";
import { PAGES, REFUSED_QUERY } from "../lib/access";
import { CLIENT_KEY, ApiError, errorText } from "../lib/client";
import { formatDayText } from "../lib/format";
import { isAdmin } from "../lib/roles";
import { createCompetitionsApi } from "../services/competitions";
import { isArchived, isPast, podiumIcon, rankingColor, todayIso, type Competition, type Participant } from "./competitions/competitions";

const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
const comps = ref<Competition[]>([]);
/** Why the widgets are empty when the server refused or failed; offline, they just stay empty. */
const loadError = ref("");

onMounted(async () => {
  try {
    comps.value = await competitionsApi.list();
  } catch (e) {
    loadError.value = e instanceof ApiError && e.status === 0 ? "" : errorText(e);
  }
});

// Local date; a competition is upcoming until its last day, an undated one is never past
const today = todayIso();
const upcomingComps = computed(() =>
  comps.value
    .filter((c) => !isPast(c, today) && !isArchived(c))
    // Soonest first, the undated ones (« Date à venir ») last
    .sort(
      (a, b) =>
        Number(!a.date_competition) - Number(!b.date_competition) || (a.date_competition ?? "").localeCompare(b.date_competition ?? ""),
    )
    .slice(0, 3),
);

// Only competitions already over (archived or not): an upcoming or undated one never shows here
const pastResultsComps = computed(() =>
  comps.value
    .filter((c) => isPast(c, today))
    .sort((a, b) => (b.date_competition || "").localeCompare(a.date_competition || ""))
    .slice(0, 3),
);

const BANNER = "https://alj-escalade.fr/wp-content/uploads/2026/09/De-nouveaux-blocs-tous-les-15-jours-3-1024x512.png";

// Sent back by the router guards from an admin page: only a known page is named
const route = useRoute();
const refused = computed(() => PAGES.find((p) => p.href === route.query[REFUSED_QUERY])?.label);
</script>

<template>
  <AppShell page="accueil" title="Bureau">
    <template #default="{ role }">
      <p class="mb-4 text-sm text-slate-600">Bienvenue sur le nouvel espace de gestion de l'ALJ Escalade</p>
      <p
        v-if="refused"
        id="refused-page"
        role="status"
        class="mb-3.5 rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-2.5 text-[13px] text-amber-900"
      >
        ⛔ La page {{ refused }} est réservée aux administrateurs.
      </p>

      <p v-if="loadError" data-testid="home-load-error" role="alert" class="mb-3 text-[13px] text-red-700">⚠️ {{ loadError }}</p>
      <div class="grid gap-4 md:grid-cols-2" data-testid="home-widgets">
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="upcoming-widget">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5">📅 Prochaines compétitions</h3>
            <RouterLink to="/bureau/competitions" class="text-xs font-semibold text-accent hover:underline">Tout voir ›</RouterLink>
          </div>
          <div v-if="!upcomingComps.length" class="text-xs text-slate-400 italic py-2">Aucune compétition à venir programmée.</div>
          <div v-else class="flex flex-col gap-2">
            <RouterLink
              v-for="c in upcomingComps"
              :key="c.id"
              :to="{ path: '/bureau/competitions', query: { id: String(c.id) } }"
              class="rounded-lg border border-slate-100 bg-slate-50/50 p-2.5 text-xs text-slate-700 hover:border-accent hover:bg-white no-underline transition-colors flex items-start justify-between gap-2"
              data-testid="upcoming-comp-item"
            >
              <div>
                <b class="text-slate-900 block text-[13px]">{{ c.nom }}</b>
                <div class="text-slate-500 mt-0.5">
                  📅 {{ c.date_competition ? formatDayText(c.date_competition) : "Date à venir" }}
                  <span v-if="c.lieu">· 📍 {{ c.lieu }}</span>
                </div>
              </div>
              <UiBadge v-if="c.type" variant="soft" color="blue" class="shrink-0 text-[10.5px]">
                {{ c.type }}
              </UiBadge>
            </RouterLink>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="results-widget">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5">🏆 Derniers résultats</h3>
            <RouterLink to="/bureau/competitions" class="text-xs font-semibold text-accent hover:underline">Voir l'historique ›</RouterLink>
          </div>
          <div v-if="!pastResultsComps.length" class="text-xs text-slate-400 italic py-2">Aucun résultat récent disponible.</div>
          <div v-else class="flex flex-col gap-2">
            <div
              v-for="c in pastResultsComps"
              :key="c.id"
              class="rounded-lg border border-slate-100 bg-slate-50/50 p-2.5 text-xs text-slate-700"
              data-testid="past-result-item"
            >
              <div class="flex items-center justify-between gap-1 mb-1">
                <b class="text-slate-900 truncate">{{ c.nom }}</b>
                <span class="text-slate-400 text-[11px] shrink-0">{{ c.date_competition ? formatDayText(c.date_competition) : "" }}</span>
              </div>
              <div
                v-if="(c.participants || []).filter((p: Participant) => p.classement || p.resultat_ffme).length"
                class="flex flex-wrap gap-1 mt-1"
              >
                <UiBadge
                  v-for="(p, idx) in (c.participants || []).filter((p: Participant) => p.classement || p.resultat_ffme).slice(0, 3)"
                  :key="p.adherent_id ?? idx"
                  :color="rankingColor(p)"
                  variant="soft"
                  data-testid="past-result-ranking"
                >
                  {{ podiumIcon(p) || (p.classement ? `#${p.classement}` : "") }}
                  {{ p.prenom }} {{ p.nom }}
                </UiBadge>
              </div>
              <div v-else class="text-[11px] text-slate-400 italic">{{ (c.participants || []).length }} participant(s)</div>
            </div>
          </div>
        </div>
      </div>

      <img
        :src="BANNER"
        alt="De nouveaux blocs tous les 15 jours — ALJ Escalade"
        loading="lazy"
        class="mt-5.5 max-h-[480px] w-full rounded-2xl border border-slate-200 object-cover shadow-md"
      />
      <p class="mt-4.5 text-slate-500">
        Connecté en tant que {{ isAdmin(role) ? "administrateur" : "coach" }}. Les données sont lues depuis la base du club et actualisées
        automatiquement.
      </p>
    </template>
  </AppShell>
</template>
