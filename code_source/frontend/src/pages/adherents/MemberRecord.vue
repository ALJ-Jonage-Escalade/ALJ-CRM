<script setup lang="ts">
/* Read view of a member record: status, slot, every known field. Admins get the edit form, which the page opens in a
   dialog; the other actions are in the « Plus » menu: e-mail (coaches and admins), call, payment certificate and detach
   from HelloAsso (admins, online only).
   compact: a narrow column (the page's side panel), each label above its value. */
import { computed, inject, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import UiBadge from "../../components/ui/UiBadge.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiMenu from "../../components/ui/UiMenu.vue";
import UiMenuItem from "../../components/ui/UiMenuItem.vue";
import { ApiError, CLIENT_KEY, errorText } from "../../lib/client";
import { formatDayText } from "../../lib/format";
import { telHref } from "../../lib/text";
import { useNetworkUp } from "../../composables/network";
import { isCompetitor, type Member } from "./members";
import { paymentBadge, type Competition, type Participant } from "../competitions/competitions";
import { recordRows } from "./record";
import { createCompetitionsApi } from "../../services/competitions";

const props = defineProps<{ member: Member; admin: boolean; compact?: boolean }>();
const emit = defineEmits<{ email: []; attestation: []; edit: []; detach: [] }>();

const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
const networkUp = useNetworkUp();
const tab = ref<"general" | "competitions">("general");
const competitions = ref<Competition[]>([]);
/** Why the competitions tab is empty when the server refused or failed; offline, it just stays empty. */
const competitionsError = ref("");

onMounted(async () => {
  try {
    competitions.value = await competitionsApi.list();
  } catch (e) {
    competitionsError.value = e instanceof ApiError && e.status === 0 ? "" : errorText(e);
  }
});

const memberCompetitions = computed(() => {
  const memberId = props.member.user_id;
  return competitions.value
    .map((competition) => ({
      ...competition,
      participant: (competition.participants || []).find((participant: Participant) => participant.adherent_id === memberId),
    }))
    .filter((competition) => competition.participant)
    .sort((a, b) => (b.date_competition || "").localeCompare(a.date_competition || ""));
});

const rows = computed(() => recordRows(props.member));

/** Dials the number: a menu item cannot be a tel: link, so it opens the link itself. */
function call(phone: string): void {
  window.location.href = telHref(phone);
}
</script>

<template>
  <div data-testid="member-record-view" class="flex flex-col gap-3">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div class="flex min-w-0 flex-1 flex-col gap-3">
        <div class="flex flex-row items-start justify-between gap-2 text-lg font-bold text-slate-800">
          <div class="flex flex-wrap items-center gap-1.5">
            <span data-testid="record-name">{{ member.first_name }} {{ member.last_name }}</span>
            <UiBadge v-if="isCompetitor(member)" variant="soft" color="violet" class="text-[10.5px]">🏆 Compétiteur</UiBadge>
          </div>
          <div>
            <slot name="status" />
          </div>
        </div>
        <div class="flex flex-col gap-2 text-xs text-slate-500">
          <div>{{ member.tarif_name || "—" }}</div>
          <div>Saison {{ member.season_name }}</div>
        </div>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2" data-testid="record-actions">
      <UiButton v-if="admin" variant="muted" small data-testid="record-edit" title="Modifier la fiche adhérent" @click="emit('edit')">
        ✏️ Modifier
      </UiButton>
      <UiMenu label="⋯ Plus" small align="start" aria-label="Plus d'actions" data-testid="record-more">
        <UiMenuItem data-testid="record-email" title="Envoyer un e-mail à cet adhérent" @select="emit('email')">✉️ E-mail</UiMenuItem>
        <UiMenuItem v-if="member.phone" data-testid="record-call" @select="call(member.phone)">📞 Appeler</UiMenuItem>
        <UiMenuItem v-if="admin" data-testid="record-attestation" title="Attestation de paiement (PDF)" @select="emit('attestation')">
          📄 Attestation
        </UiMenuItem>
        <UiMenuItem
          v-if="admin && member.helloasso_item_id !== null"
          danger
          data-testid="record-detach"
          :disabled="!networkUp"
          :title="
            networkUp ? 'Supprimer cette adhésion, issue d\'une inscription HelloAsso rattachée au mauvais adhérent' : 'Connexion requise'
          "
          @select="emit('detach')"
        >
          🔗 Détacher de HelloAsso
        </UiMenuItem>
      </UiMenu>
      <span v-if="!admin" data-testid="record-readonly" class="text-[11.5px] text-slate-500 italic">
        👁️ Modification et attestation réservées aux administrateurs
      </span>
    </div>

    <div class="flex border-b border-slate-200 text-xs font-semibold" data-testid="record-tabs">
      <button
        type="button"
        :class="[
          'px-3 py-1.5 border-b-2 cursor-pointer transition-colors',
          tab === 'general' ? 'border-accent text-accent' : 'border-transparent text-slate-500 hover:text-slate-800',
        ]"
        data-testid="record-tab-general"
        @click="tab = 'general'"
      >
        📋 Fiche adhérent
      </button>
      <button
        type="button"
        :class="[
          'px-3 py-1.5 border-b-2 cursor-pointer transition-colors flex items-center gap-1',
          tab === 'competitions' ? 'border-accent text-accent' : 'border-transparent text-slate-500 hover:text-slate-800',
        ]"
        data-testid="record-tab-competitions"
        @click="tab = 'competitions'"
      >
        🏆 Compétitions
        <span class="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
          {{ memberCompetitions.length }}
        </span>
      </button>
    </div>

    <dl v-if="tab === 'general'" data-testid="record-fields" class="divide-y divide-slate-100 rounded-lg text-[12.5px]">
      <div
        v-for="row in rows"
        :key="row.label"
        data-testid="record-field"
        :class="compact ? 'px-3 py-1.5' : 'grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)] gap-3 px-3 py-1.5'"
      >
        <dt :class="['font-semibold text-slate-500', compact && 'text-[11.5px]']">{{ row.icon }} {{ row.label }}</dt>
        <dd class="wrap-break-word whitespace-pre-line text-slate-800">
          <RouterLink v-if="row.to" :to="row.to" data-testid="record-field-link" class="text-accent hover:underline">
            {{ row.value }}
          </RouterLink>
          <template v-else>{{ row.value }}</template>
        </dd>
      </div>
    </dl>

    <div v-else class="flex flex-col gap-2 text-xs" data-testid="record-competitions-list">
      <p v-if="competitionsError" data-testid="record-competitions-error" role="alert" class="text-red-700">⚠️ {{ competitionsError }}</p>
      <div v-else-if="!memberCompetitions.length" class="text-xs text-slate-400 italic py-4 text-center">
        Cet adhérent n'est inscrit à aucune compétition.
      </div>
      <div
        v-for="c in memberCompetitions"
        :key="c.id"
        class="rounded-lg border border-slate-200 bg-slate-50/50 p-2.5 flex flex-col gap-1"
        data-testid="member-comp-item"
      >
        <div class="flex items-start justify-between gap-1">
          <RouterLink
            :to="{ path: '/bureau/competitions', query: { id: String(c.id) } }"
            class="font-bold text-slate-900 hover:underline hover:text-accent"
          >
            {{ c.nom }}
          </RouterLink>
          <UiBadge v-if="c.type" variant="soft" color="blue" class="text-[10px] shrink-0">
            {{ c.type }}
          </UiBadge>
        </div>
        <div class="text-[11.5px] text-slate-500">
          📅 {{ c.date_competition ? formatDayText(c.date_competition) : "Date non précisée" }}
          <span v-if="c.lieu">· 📍 {{ c.lieu }}</span>
        </div>
        <div v-if="c.participant" class="flex flex-wrap items-center gap-1.5 mt-1 text-[11px]">
          <span
            :class="[
              'rounded px-1.5 py-0.5 font-semibold',
              c.participant.selectionne ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600',
            ]"
          >
            {{ c.participant.selectionne ? "✓ Sélectionné" : "🔘 Non invité" }}
          </span>
          <UiBadge variant="soft" :color="paymentBadge(c.participant.statut_paiement).color" class="text-[11px]">
            {{ paymentBadge(c.participant.statut_paiement).label }}
          </UiBadge>
          <span v-if="c.participant.classement" class="rounded bg-violet-50 px-1.5 py-0.5 font-bold text-violet-700">
            🏅 Rang : {{ c.participant.classement }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
