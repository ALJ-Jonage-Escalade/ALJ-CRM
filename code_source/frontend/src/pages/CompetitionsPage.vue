<script setup lang="ts">
/* Compétitions (/competitions and /bureau/competitions, any role: read-only accounts too, as on the former phone
   page): the competitions, then one competition's participants with their payment status, read only. On phones the
   list or the competition (?id=<id>); on desktop both side by side. Kept up to date by polling, readable offline
   (plan D2): the competitions, and for coaches and admins the competitors' contacts, are kept on the device under the
   former page's names, so what it stored is shown too. The changes are made on the former pages (MANAGE_*) until
   plan phase 11. /competitions is also where the Google sign-in ends (composables/signIn.ts): its error shows here. */
import { computed, inject, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";
import { AUTH_KEY } from "../composables/auth";
import { SIGN_IN_ERROR_KEY } from "../composables/signIn";
import { useSyncedResource } from "../composables/syncedResource";
import { pageAccess, verdict } from "../lib/access";
import { isStaff } from "../lib/roles";
import { telHref } from "./adherents/members";
import {
  countLine, counts, euros, filterRows, groupRows, hasResults, isArchived, MANAGE_DESKTOP, MANAGE_PHONE, participantRows, payment, period,
  sortCompetitions, toMemberSlots, type Competition, type CompetitorContact, type MemberSlot, type ParticipantFilter,
} from "./competitions/competitions";

const auth = inject(AUTH_KEY)!;
const signInError = inject(SIGN_IN_ERROR_KEY, ref(null));
const route = useRoute();

const access = computed(() => verdict(auth.state.value, pageAccess("competitions"), true));
const open = computed(() => access.value === "allow" || access.value === "offline");
const uid = computed(() => {
  const s = auth.state.value;
  return open.value && (s.status === "signedIn" || s.status === "error") ? s.user.uid : null;
});
// Coaches and admins see the contacts; offline the role is unknown: only a copy kept for this user can show
const staff = computed(() => auth.state.value.status === "signedIn" && isStaff(auth.state.value.role));
const contactsShown = computed(() => staff.value || access.value === "offline");

const competitions = useSyncedResource<Competition[]>("competitions", () => (open.value ? "/api/competitions" : null), { offline: true, uid });
const competitors = useSyncedResource<CompetitorContact[]>("competitors", () => (open.value && contactsShown.value ? "/api/members/competitors" : null), { offline: true, uid });
// Current tariff and slot group of the members, to group the participants: online only (the directory stays on the server)
const members = useSyncedResource<MemberSlot[]>("competition-members", () => (open.value && auth.state.value.status === "signedIn" ? "/api/competition-members" : null), {
  offline: false, select: toMemberSlots, intervalMs: 60_000,
});

const all = computed(() => sortCompetitions(competitions.data.value ?? []));
const current = computed(() => all.value.filter((c) => !isArchived(c)));
const archived = computed(() => all.value.filter(isArchived));
const showArchived = ref(false);

const selectedId = computed(() => (typeof route.query.id === "string" ? route.query.id : ""));
const selected = computed(() => all.value.find((c) => String(c.id) === selectedId.value));

const filter = ref<ParticipantFilter>("all");
const rows = computed(() => (selected.value ? participantRows(selected.value, members.data.value ?? [], contactsShown.value ? (competitors.data.value ?? []) : []) : []));
const kpis = computed(() => counts(rows.value));
const groups = computed(() => groupRows(filterRows(rows.value, filter.value)));
const FILTERS: { id: ParticipantFilter; label: string; count: (c: typeof kpis.value) => number }[] = [
  { id: "all", label: "📋 Tous", count: (c) => c.all },
  { id: "selected", label: "✅ Participe : Oui", count: (c) => c.selected },
  { id: "unpaid", label: "⏳ Paiement en attente", count: (c) => c.unpaid },
];

const plural = (n: number) => (n > 1 ? "s" : "");
const listLine = computed(() => {
  if (!competitions.data.value) return competitions.state.value === "loading" ? "⏳ Chargement des compétitions…" : "Aucune donnée des compétitions sur cet appareil.";
  const n = current.value.length;
  const a = archived.value.length;
  return `${n} compétition${plural(n)}${a ? ` · ${a} archivée${plural(a)}` : ""}`;
});

const TIME = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });
const syncInfo = computed(() => {
  const at = competitions.dataAt.value;
  const since = at ? ` — données du ${TIME.format(at)}` : "";
  const state = competitions.state.value;
  if (competitions.httpStatus.value === 403) return "🔒 Accès restreint";
  if (state === "offline" || auth.state.value.status === "error") return `📴 Hors ligne${since || " : aucune donnée sur cet appareil"}`;
  if (state === "error") return `⚠️ Serveur injoignable — nouvel essai automatique${since}`;
  if (state === "loading") return at ? `💾 Données du ${TIME.format(at)}` : "";
  return at ? `☁️ À jour — ${TIME.format(at)}` : "";
});

const chip = (active: boolean) => [
  "cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold",
  active ? "border-accent bg-accent text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
];
const manageButton = "items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-[13px] font-bold text-white no-underline hover:bg-accent-dark";
const telButton = "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11.5px] font-semibold no-underline";
</script>

<template>
  <AppShell page="competitions" title="Compétitions" :sync="syncInfo" offline-read>
    <p v-if="signInError" data-testid="sign-in-error" role="alert" class="mb-3 rounded-lg border border-red-300 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800">❌ {{ signInError }}</p>

    <div v-if="staff" class="mb-3 flex flex-wrap items-center gap-2">
      <a :href="MANAGE_PHONE" data-testid="manage-link" :class="[manageButton, 'inline-flex md:hidden']">✏️ Gérer les compétitions</a>
      <a :href="MANAGE_DESKTOP" data-testid="manage-link-desktop" :class="[manageButton, 'hidden md:inline-flex']">✏️ Gérer les compétitions</a>
      <span class="text-xs text-slate-500">Créer, modifier, inscrire, paiements HelloAsso, e-mails : sur la page de gestion.</span>
    </div>

    <div class="md:grid md:grid-cols-[minmax(0,360px)_minmax(0,1fr)] md:items-start md:gap-4">
      <!-- The competitions: always on desktop, on phones until one is opened -->
      <section :class="selected ? 'hidden md:block' : ''" aria-label="Liste des compétitions">
        <p class="mb-2 text-xs text-slate-500" data-testid="comp-count">{{ listLine }}</p>
        <ul class="flex flex-col gap-2">
          <li v-if="competitions.data.value && !current.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">
            {{ archived.length ? "Aucune compétition en cours : toutes sont archivées." : "Aucune compétition enregistrée." }}
          </li>
          <li v-for="c in current" :key="c.id">
            <RouterLink
              :to="{ query: { ...route.query, id: String(c.id) } }"
              data-testid="comp-card"
              :aria-current="selected?.id === c.id ? 'true' : undefined"
              :class="['block rounded-xl border bg-white px-3.5 py-3 text-slate-800 no-underline shadow-sm hover:border-accent', selected?.id === c.id ? 'border-accent' : 'border-slate-200']"
            >
              <b class="block text-[15px]" data-testid="comp-name"><span v-if="hasResults(c)" title="Résultats officiels récupérés">🏆 </span>{{ c.nom }}</b>
              <span class="block text-xs text-slate-500">🪪 {{ c.id_ffme || "—" }} · 📅 {{ period(c) }} · 💶 {{ euros(c.prix) }}</span>
              <span class="mt-0.5 block text-xs font-semibold text-blue-900">
                ({{ counts(c.participants ?? []).selected }} participant{{ plural(counts(c.participants ?? []).selected) }} · {{ counts(c.participants ?? []).unpaid }} en attente · {{ counts(c.participants ?? []).paid }} payé{{ plural(counts(c.participants ?? []).paid) }})
              </span>
              <span class="block text-xs text-slate-500">🏃 {{ c.coaches?.length ? `Coachs : ${c.coaches.join(", ")}` : "Aucun coach" }}</span>
            </RouterLink>
          </li>
        </ul>
        <button
          v-if="archived.length"
          type="button"
          data-testid="toggle-archives"
          :aria-expanded="showArchived"
          class="mt-2.5 cursor-pointer rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-300"
          @click="showArchived = !showArchived"
        >{{ showArchived ? "🙈 Masquer les archives" : `🗂 Afficher les archives (${archived.length})` }}</button>
        <ul v-if="showArchived" class="mt-2 flex flex-col gap-2" data-testid="archived-list">
          <li v-for="c in archived" :key="c.id">
            <RouterLink :to="{ query: { ...route.query, id: String(c.id) } }" data-testid="comp-card" class="block rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-slate-700 no-underline hover:border-accent">
              <b class="block text-[14px]" data-testid="comp-name">{{ c.nom }}</b>
              <span class="block text-xs text-slate-500">📅 {{ period(c) }} · 📦 Archivée</span>
            </RouterLink>
          </li>
        </ul>
      </section>

      <!-- One competition -->
      <section v-if="selected" data-testid="comp-detail" aria-label="Compétiteurs">
        <RouterLink :to="{ query: {} }" data-testid="back-link" class="mb-2 inline-block text-[13px] font-semibold text-accent no-underline md:hidden">‹ Toutes les compétitions</RouterLink>
        <div class="mb-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <h2 class="m-0 text-[17px] font-bold" data-testid="detail-name">{{ selected.nom }}</h2>
          <p class="mt-0.5 text-xs text-slate-500">
            🪪 {{ selected.id_ffme || "—" }} · 📅 {{ period(selected) }} · 💶 {{ euros(selected.prix) }}<template v-if="isArchived(selected)"> · 📦 Archivée</template>
          </p>
          <p class="mt-0.5 text-xs text-slate-500">🏃 {{ selected.coaches?.length ? `Coachs : ${selected.coaches.join(", ")}` : "Aucun coach" }}</p>
          <a
            v-if="selected.whatsapp_link"
            :href="selected.whatsapp_link"
            target="_blank"
            rel="noopener noreferrer"
            class="mt-1.5 inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-2 py-0.5 text-xs font-bold text-green-700 no-underline"
          >💬 Groupe WhatsApp ↗</a>
          <div class="mt-3 grid grid-cols-3 gap-2 text-center">
            <div><div class="text-xl font-extrabold text-blue-600" data-testid="kpi-selected">{{ kpis.selected }}</div><div class="text-[11px] font-semibold text-slate-500">Participe</div></div>
            <div><div class="text-xl font-extrabold text-amber-600" data-testid="kpi-unpaid">{{ kpis.unpaid }}</div><div class="text-[11px] font-semibold text-slate-500">Paiement en attente</div></div>
            <div><div class="text-xl font-extrabold text-green-600" data-testid="kpi-paid">{{ kpis.paid }}</div><div class="text-[11px] font-semibold text-slate-500">Paiement validé</div></div>
          </div>
        </div>

        <div class="mb-2 flex flex-wrap gap-1.5">
          <button
            v-for="f in FILTERS"
            :key="f.id"
            type="button"
            :data-testid="`filter-${f.id}`"
            :aria-pressed="filter === f.id"
            :class="chip(filter === f.id)"
            @click="filter = f.id"
          >{{ f.label }} ({{ f.count(kpis) }})</button>
        </div>
        <p class="mb-2 text-xs text-slate-500" data-testid="participant-count">{{ countLine(kpis, filter) }}</p>

        <p v-if="!groups.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">
          {{ rows.length ? "Aucun compétiteur ne correspond au filtre." : "Aucun compétiteur inscrit." }}
        </p>
        <div v-for="[group, list] in groups" :key="group" class="mb-3" data-testid="participant-group">
          <h3 class="mb-1.5 text-xs font-bold text-slate-600 uppercase">{{ group }} · {{ list.length }} compétiteur{{ plural(list.length) }}</h3>
          <ul class="grid gap-2 xl:grid-cols-2">
            <li v-for="p in list" :key="p.adherent_id ?? `${p.nom}-${p.prenom}`" data-testid="participant-card" class="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 shadow-sm">
              <div class="flex items-start justify-between gap-2">
                <span class="min-w-0">
                  <b class="block text-[14.5px]" data-testid="participant-name">{{ p.nom }} {{ p.prenom }}</b>
                  <span class="block text-xs text-slate-500">
                    🪪 {{ p.num_licence || "sans licence" }} · {{ p.tarif || "—" }}
                    <template v-if="staff && p.commande_helloasso"> · 🧾 {{ p.commande_helloasso }}</template>
                    <template v-if="staff && p.note_paiement"> · 📝 {{ p.note_paiement }}</template>
                  </span>
                </span>
                <span :class="['shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-bold text-white', payment(p.statut_paiement).class]" data-testid="payment-badge" title="Statut de paiement">{{ payment(p.statut_paiement).label }}</span>
              </div>
              <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
                <span data-testid="participe" :class="['rounded-md px-2 py-0.5 text-[11.5px] font-bold', p.selectionne ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-500']">
                  {{ p.selectionne ? "✅ Participe" : "— Ne participe pas" }}
                </span>
                <span v-if="p.resultat_ffme || p.classement" class="rounded-md bg-amber-50 px-2 py-0.5 text-[11.5px] font-bold text-amber-800">🏅 {{ p.resultat_ffme || p.classement }}</span>
                <template v-if="contactsShown">
                  <a v-if="p.phone" :href="telHref(p.phone)" :class="[telButton, 'border-blue-200 bg-blue-50 text-blue-700']">📞 {{ p.phone }}</a>
                  <a
                    v-for="e in p.emergency"
                    :key="e.phone"
                    :href="telHref(e.phone)"
                    title="Contact d'urgence"
                    data-testid="emergency-link"
                    :class="[telButton, 'border-red-200 bg-red-50 text-red-700']"
                  >🚨 {{ e.name || "Urgence" }} · {{ e.phone }}</a>
                </template>
              </div>
            </li>
          </ul>
        </div>
      </section>
      <p v-else class="hidden rounded-xl border border-dashed border-slate-300 px-4 py-10 text-center text-slate-500 md:block">
        {{ selectedId && competitions.data.value ? "Compétition introuvable." : "Sélectionnez une compétition pour voir ses compétiteurs." }}
      </p>
    </div>
  </AppShell>
</template>
