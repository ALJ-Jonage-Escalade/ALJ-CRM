<script setup lang="ts">
/* Annuaire (/index, coaches and admins): the members of a season, read only, on phones (one tab at a time) as on
   desktop (filters beside the list). Members tab: search, cards unfolded on demand (contacts, emergency contacts,
   diplomas); Urgences tab: a member's phones from 2 letters of their name; filters: season, status, slots / tariffs.
   Readable offline (plan D2): the last list received is kept on the device for its user (directory.ts says which
   fields) and shown when the network is down, with its date; wiped on logout, 401/403, another account, after 30 days.
   The filters are remembered as on the former page (web/index.html), without the search. */
import { computed, inject, ref, watch } from "vue";
import AppShell from "../components/AppShell.vue";
import UiBadge from "../components/ui/UiBadge.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiCard from "../components/ui/UiCard.vue";
import { AUTH_KEY } from "../composables/auth";
import { useSyncedResource } from "../composables/syncedResource";
import { localStorageOrNone } from "../lib/localStorage";
import { pageVerdict } from "../lib/access";
import { formatDateTime } from "../lib/format";
import {
  allowedTarifs,
  checkAll,
  creneauItems,
  diplomes,
  filterMembers,
  groupChecked,
  loadFilters,
  OTHER_PREFIX,
  otherChecked,
  saveFilters,
  statusChips,
  statusColor,
  tarifCounts,
  type CreneauItem,
} from "./adherents/members";
import {
  detailRows,
  DIRECTORY_FILTERS_STORAGE,
  emergencyMatches,
  emergencyRows,
  EMERGENCY_MIN_LETTERS,
  seasonCounts,
  toDirectory,
  type DirectoryMember,
} from "./annuaire/directory";
import { plural, telHref } from "../lib/text";
import { membersRead } from "../services/members";

const auth = inject(AUTH_KEY)!;

const filters = ref(loadFilters(localStorageOrNone(), DIRECTORY_FILTERS_STORAGE));
watch(filters, (f) => saveFilters(f, localStorageOrNone(), DIRECTORY_FILTERS_STORAGE), { deep: true });

// Nothing is asked (nor read from the device) for an account the page does not open to
const open = computed(() => ["allow", "offline"].includes(pageVerdict(auth.state.value, "annuaire")));
const uid = computed(() => {
  const s = auth.state.value;
  return open.value && (s.status === "signedIn" || s.status === "error") ? s.user.uid : null;
});

const seasons = useSyncedResource("seasons", () => (open.value ? { path: "/api/seasons" } : null), {
  offline: true,
  uid,
  intervalMs: 60_000,
});
const directory = useSyncedResource("directory", () => (open.value ? membersRead(filters.value.season) : null), {
  offline: true,
  uid,
  select: toDirectory,
});
// A season that no longer exists (remembered from an earlier visit): back to the active one
watch(directory.httpStatus, (status) => {
  if (status === 404 && filters.value.season) {
    filters.value.season = "";
  }
});

const list = computed(() => directory.data.value);
const season = computed(() => list.value?.season ?? filters.value.season);
const all = computed<readonly DirectoryMember[]>(() => list.value?.members ?? []);
const items = computed(() => creneauItems(list.value?.creneaux ?? []));
const counts = computed(() => tarifCounts(all.value, items.value));
const otherTarifs = computed(() => Object.keys(counts.value.others).sort((a, b) => a.localeCompare(b, "fr")));
const shown = computed(() =>
  filterMembers(all.value, filters.value, allowedTarifs(items.value, counts.value, filters.value))
    .slice()
    .sort((a, b) => a.last_name.localeCompare(b.last_name, "fr") || a.first_name.localeCompare(b.first_name, "fr")),
);
const chips = computed(() => statusChips(all.value));
const kpis = computed(() => seasonCounts(all.value));
const countLine = computed(() => {
  if (!list.value) {
    return directory.state.value === "loading" ? "⏳ Chargement de l'annuaire…" : "Aucune donnée de l'annuaire sur cet appareil.";
  }
  const n = shown.value.length;
  return `${n} adhérent${plural(n)} affiché${plural(n)} · saison ${season.value}${filters.value.status ? ` · statut ${filters.value.status}` : ""}`;
});

const syncInfo = computed(() => {
  const at = directory.dataAt.value;
  const since = at ? ` — données du ${formatDateTime(at)}` : "";
  const state = directory.state.value;
  if (directory.httpStatus.value === 403) {
    return "🔒 Accès réservé aux coachs";
  }
  if (state === "offline" || auth.state.value.status === "error") {
    return `📴 Hors ligne${since || " : aucune donnée sur cet appareil"}`;
  }
  if (state === "error") {
    return `⚠️ Chargement impossible — nouvel essai automatique${since}`;
  }
  if (state === "loading") {
    return at ? `💾 Données du ${formatDateTime(at)}` : "";
  }
  return "";
});

// Tabs (phones); on desktop the filters stay beside the list
type Tab = "members" | "urgency" | "filters";
const tab = ref<Tab>("members");
const TABS: { id: Tab; label: string; desktop: boolean }[] = [
  { id: "members", label: "👥 Adhérents", desktop: true },
  { id: "urgency", label: "🚨 Urgences", desktop: true },
  { id: "filters", label: "🔎 Filtres", desktop: false },
];

const unfolded = ref(new Set<number>());
function toggle(m: DirectoryMember): void {
  const next = new Set(unfolded.value);
  if (!next.delete(m.purchase_id)) {
    next.add(m.purchase_id);
  }
  unfolded.value = next;
}

const urgencySearch = ref("");
const urgency = computed(() => emergencyMatches(all.value, urgencySearch.value));

function chooseSeason(name: string): void {
  filters.value.season = name;
}
function toggleGroup(it: CreneauItem, on: boolean): void {
  filters.value.groups[it.raw] = on;
}
function toggleOther(tarif: string, on: boolean): void {
  filters.value.others[OTHER_PREFIX + tarif] = on;
}
function setAll(on: boolean): void {
  filters.value = checkAll(filters.value, items.value, counts.value, on);
}
function chooseStatus(value: string): void {
  filters.value.status = value;
}

const chip = (active: boolean) => [
  "cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold",
  active ? "border-accent bg-accent text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
];
const callButton =
  "inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs font-bold text-slate-700 no-underline hover:bg-slate-200";
const searchInput = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-[15px] md:text-[13px]";
</script>

<template>
  <AppShell page="annuaire" title="Annuaire" :sync="syncInfo">
    <div class="mb-3 flex gap-1.5" role="tablist" aria-label="Vues de l'annuaire">
      <button
        v-for="t in TABS"
        :key="t.id"
        type="button"
        role="tab"
        :data-testid="`tab-${t.id}`"
        :aria-selected="tab === t.id"
        :class="[chip(tab === t.id), 'px-3.5 py-1.5 text-[13px]', !t.desktop && 'md:hidden']"
        @click="tab = t.id"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="md:grid md:grid-cols-[260px_minmax(0,1fr)] md:items-start md:gap-4">
      <!-- Filters: a tab on phones, beside the list on desktop -->
      <aside
        :class="[tab === 'filters' ? 'flex' : 'hidden md:flex', 'flex-col gap-3']"
        data-testid="directory-filters"
        aria-label="Filtres"
      >
        <UiCard>
          <h3 class="mb-1.5 text-sm font-bold">📅 Saison</h3>
          <select
            :value="season"
            data-testid="season-select"
            aria-label="Saison"
            class="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]"
            @change="chooseSeason(($event.target as HTMLSelectElement).value)"
          >
            <option v-if="!seasons.data.value?.seasons.includes(season) && season" :value="season">{{ season }}</option>
            <option v-for="s in seasons.data.value?.seasons ?? []" :key="s" :value="s">
              {{ s }}{{ s === seasons.data.value?.active ? " (saison active)" : "" }}
            </option>
          </select>
        </UiCard>
        <UiCard>
          <h3 class="mb-1.5 text-sm font-bold">📌 Statut de l'inscription</h3>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="c in chips"
              :key="c.value"
              type="button"
              :data-testid="`status-${c.value || 'all'}`"
              :aria-pressed="filters.status === c.value"
              :class="chip(filters.status === c.value)"
              @click="chooseStatus(c.value)"
            >
              {{ c.label }} ({{ c.count }})
            </button>
          </div>
        </UiCard>
        <UiCard>
          <h3 class="mb-1 text-sm font-bold">🧗 Créneaux affichés</h3>
          <p class="mb-2 text-[11.5px] text-slate-500">
            Un créneau regroupe un ou plusieurs tarifs HelloAsso. Par défaut, les listes d'attente sont exclues.
          </p>
          <template v-for="it in items" :key="`${it.kind}:${it.raw}`">
            <div v-if="it.kind === 'section'" class="mt-2 text-xs font-bold text-slate-700">📁 {{ it.label }}</div>
            <div v-else-if="it.kind === 'sub'" class="mt-1 pl-2 text-[11.5px] font-semibold text-slate-500">📂 {{ it.label }}</div>
            <label v-else data-testid="filter-group" class="flex cursor-pointer items-center gap-2 py-1 text-[13px]">
              <input
                type="checkbox"
                class="size-4 accent-accent"
                :checked="groupChecked(filters, it)"
                @change="toggleGroup(it, ($event.target as HTMLInputElement).checked)"
              />
              <span class="min-w-0 flex-1 truncate" :title="it.raw">{{ it.label }}</span>
              <span class="rounded-full bg-slate-200 px-2 text-[11px] font-semibold text-slate-600">{{ counts.groups[it.raw] ?? 0 }}</span>
            </label>
          </template>
          <template v-if="otherTarifs.length">
            <div class="mt-2 text-xs font-bold text-slate-700">📁 Autres tarifs (hors créneau)</div>
            <label
              v-for="t in otherTarifs"
              :key="t"
              data-testid="filter-group"
              class="flex cursor-pointer items-center gap-2 py-1 text-[13px]"
            >
              <input
                type="checkbox"
                class="size-4 accent-accent"
                :checked="otherChecked(filters, t)"
                @change="toggleOther(t, ($event.target as HTMLInputElement).checked)"
              />
              <span class="min-w-0 flex-1 truncate">{{ t }}</span>
              <span class="rounded-full bg-slate-200 px-2 text-[11px] font-semibold text-slate-600">{{ counts.others[t] }}</span>
            </label>
          </template>
          <div class="mt-2.5 flex gap-1.5">
            <UiButton variant="muted" small data-testid="filter-all" @click="setAll(true)">Tout cocher</UiButton>
            <UiButton variant="muted" small data-testid="filter-none" @click="setAll(false)">Tout décocher</UiButton>
          </div>
        </UiCard>
      </aside>

      <!-- Members -->
      <section v-if="tab === 'members' || tab === 'filters'" :class="tab === 'filters' && 'hidden md:block'" aria-label="Adhérents">
        <div class="mb-3 grid grid-cols-3 gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-center shadow-sm">
          <div>
            <div class="text-xl font-bold text-blue-600" data-testid="kpi-shown">{{ list ? shown.length : "—" }}</div>
            <div class="text-[11px] text-slate-500">Affichés</div>
          </div>
          <div>
            <div class="text-xl font-bold" data-testid="kpi-season">{{ list ? kpis.registered : "—" }}</div>
            <div class="text-[11px] text-slate-500">Inscrits saison</div>
          </div>
          <div>
            <div class="text-xl font-bold text-red-600" data-testid="kpi-cancelled">{{ list ? kpis.cancelled : "—" }}</div>
            <div class="text-[11px] text-slate-500">Annulés saison</div>
          </div>
        </div>
        <input
          v-model="filters.search"
          type="search"
          data-testid="directory-search"
          aria-label="Rechercher un adhérent"
          placeholder="🔍 Nom, prénom, tarif, licence, ville, téléphone…"
          :class="searchInput"
        />
        <p class="my-2 text-xs text-slate-500" data-testid="directory-count">{{ countLine }}</p>
        <ul class="grid gap-2 lg:grid-cols-2 2xl:grid-cols-3">
          <li
            v-if="list && !shown.length"
            class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500 lg:col-span-full"
          >
            Aucun adhérent ne correspond aux filtres.
          </li>
          <li
            v-for="m in shown"
            :key="m.purchase_id"
            data-testid="directory-card"
            class="rounded-xl border border-slate-200 bg-white px-3.5 py-3 shadow-sm"
          >
            <button
              type="button"
              class="flex w-full cursor-pointer items-start justify-between gap-2 text-left"
              :aria-expanded="unfolded.has(m.purchase_id)"
              data-testid="card-toggle"
              @click="toggle(m)"
            >
              <span class="min-w-0">
                <b class="block text-[15px]">{{ m.first_name }} {{ m.last_name }}</b>
                <span class="block text-xs text-slate-500">
                  {{ m.tarif_name || "—" }}
                  <span v-for="d in diplomes(m)" :key="d.type" :title="d.label" class="pl-1">{{ d.icon }}</span>
                </span>
              </span>
              <UiBadge :color="statusColor(m.status_norm)" class="shrink-0">{{ m.status_norm || "—" }}</UiBadge>
            </button>
            <div v-if="m.phone || m.email_primary" class="mt-2 flex flex-wrap gap-1.5">
              <a v-if="m.phone" :href="telHref(m.phone)" :class="callButton">📞 Appeler</a>
              <a v-if="m.email_primary" :href="`mailto:${m.email_primary}`" :class="callButton">✉️ E-mail</a>
            </div>
            <table
              v-if="unfolded.has(m.purchase_id)"
              class="mt-2.5 w-full border-t border-dashed border-slate-200 text-[12.5px]"
              data-testid="card-details"
            >
              <tbody>
                <tr v-for="r in detailRows(m)" :key="r.label" class="align-top">
                  <th scope="row" class="w-32 py-1 pr-2 text-left font-semibold whitespace-nowrap text-slate-500">{{ r.label }}</th>
                  <td class="py-1 break-words">{{ r.value }}</td>
                </tr>
              </tbody>
            </table>
          </li>
        </ul>
      </section>

      <!-- Emergency contacts -->
      <section v-else aria-label="Contacts d'urgence">
        <input
          v-model="urgencySearch"
          type="search"
          data-testid="urgency-search"
          aria-label="Nom de l'adhérent"
          placeholder="🔍 Nom de l'adhérent…"
          :class="searchInput"
        />
        <p class="my-2 text-xs text-slate-500" data-testid="urgency-count">
          <template v-if="urgency === null">
            Tapez au moins {{ EMERGENCY_MIN_LETTERS }} lettres du nom de l'adhérent pour afficher ses contacts.
          </template>
          <template v-else>
            {{ urgency.length }} adhérent{{ plural(urgency.length) }} trouvé{{ plural(urgency.length) }} (saison {{ season }})
          </template>
        </p>
        <ul class="grid gap-2 lg:grid-cols-2">
          <li
            v-if="urgency && !urgency.length"
            class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500 lg:col-span-full"
          >
            Aucun adhérent ne correspond à cette recherche.
          </li>
          <li
            v-for="m in urgency ?? []"
            :key="m.purchase_id"
            data-testid="urgency-card"
            class="rounded-xl border border-slate-200 bg-white px-3.5 py-3 shadow-sm"
          >
            <div class="flex items-start justify-between gap-2">
              <span class="min-w-0">
                <b class="block text-[15px]">{{ m.first_name }} {{ m.last_name }}</b>
                <span class="block text-xs text-slate-500">{{ m.tarif_name || "—" }}</span>
              </span>
              <UiBadge :color="statusColor(m.status_norm)" class="shrink-0">{{ m.status_norm || "—" }}</UiBadge>
            </div>
            <div class="mt-2.5 flex flex-col gap-2 border-t border-dashed border-slate-200 pt-2.5">
              <div v-for="r in emergencyRows(m)" :key="r.label" class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
                <b class="whitespace-nowrap">{{ r.label }}</b>
                <span class="min-w-0 flex-1 break-words">{{ [r.name, r.phone].filter(Boolean).join(" · ") }}</span>
                <a v-if="r.phone" :href="telHref(r.phone)" :class="callButton">📞 Appeler</a>
              </div>
              <p v-if="!emergencyRows(m).length" class="text-xs text-slate-400">Aucun contact enregistré pour cet adhérent.</p>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </AppShell>
</template>
