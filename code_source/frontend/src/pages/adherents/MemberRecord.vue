<script setup lang="ts">
/* Read view of a member record: status, slot, every known field, call / write links. Coaches and admins can send an
   e-mail; admins also get the payment certificate and the edit form, which the page opens in a dialog. compact: a narrow
   column (the page's side panel), each label above its value. */
import { computed, inject, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import UiBadge from "../../components/ui/UiBadge.vue";
import UiButton from "../../components/ui/UiButton.vue";
import { API_KEY } from "../../lib/api";
import { formatDayText } from "../../lib/format";
import { isCompetitor, normKey, telHref, type Member } from "./members";
import type { Competition, Participant } from "../competitions/competitions";
import { recordRows } from "./record";

const props = defineProps<{ member: Member; admin: boolean; compact?: boolean }>();
const emit = defineEmits<{ email: []; attestation: []; edit: [] }>();

const api = inject(API_KEY, null);
const tab = ref<"general" | "competitions">("general");
const competitions = ref<Competition[]>([]);

onMounted(async () => {
  if (!api) {
    return;
  }
  try {
    const res = await api("/api/competitions");
    if (res.ok) {
      competitions.value = (await res.json()) as Competition[];
    }
  } catch {
    // Offline
  }
});

const memberCompetitions = computed(() => {
  const m = props.member;
  const mId = m.user_id;
  const mNom = normKey(m.last_name);
  const mPrenom = normKey(m.first_name);

  return competitions.value
    .filter((c) => {
      const parts = c.participants || [];
      return parts.some((p: Participant) => (mId && p.adherent_id === mId) || (normKey(p.nom) === mNom && normKey(p.prenom) === mPrenom));
    })
    .map((c) => {
      const part = (c.participants || []).find(
        (p: Participant) => (mId && p.adherent_id === mId) || (normKey(p.nom) === mNom && normKey(p.prenom) === mPrenom),
      );
      return {
        ...c,
        participant: part,
      };
    })
    .sort((a, b) => (b.date_competition || "").localeCompare(a.date_competition || ""));
});

const rows = computed(() => recordRows(props.member));
</script>

<template>
  <div data-testid="member-record-view" class="flex flex-col gap-3">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div class="flex min-w-0 flex-1 flex-col gap-3">
        <div class="flex flex-row items-start justify-between gap-2 text-lg font-bold text-slate-800">
          <div class="flex flex-wrap items-center gap-1.5" data-testid="record-name">
            <span>{{ member.first_name }} {{ member.last_name }}</span>
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

    <div class="flex flex-wrap gap-2">
      <UiButton small data-testid="record-email" title="Envoyer un e-mail à cet adhérent" @click="emit('email')">✉️ E-mail</UiButton>
      <template v-if="admin">
        <UiButton variant="muted" small data-testid="record-attestation" title="Attestation de paiement (PDF)" @click="emit('attestation')">
          📄 Attestation
        </UiButton>
        <UiButton
          variant="muted"
          small
          data-testid="record-edit"
          title="Modifier le créneau, les badges et les coordonnées"
          @click="emit('edit')"
        >
          ✏️ Modifier
        </UiButton>
      </template>
      <span v-else data-testid="record-readonly" class="self-center text-[11.5px] text-slate-500 italic">
        👁️ Modification et attestation réservées aux administrateurs
      </span>
    </div>
    <div class="flex flex-wrap gap-2">
      <a
        v-if="member.phone"
        :href="telHref(member.phone)"
        class="rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 no-underline"
      >
        📞 Appeler
      </a>
      <a
        v-if="member.email_primary"
        :href="`mailto:${member.email_primary}`"
        class="rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 no-underline"
      >
        ✉️ Écrire
      </a>
    </div>

    <!-- Onglets de la fiche adhérent -->
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

    <!-- Onglet 1 : Fiche générale -->
    <dl
      v-if="tab === 'general'"
      data-testid="record-fields"
      class="divide-y divide-slate-100 rounded-lg border border-slate-200 text-[12.5px]"
    >
      <div
        v-for="row in rows"
        :key="row.label"
        data-testid="record-field"
        :class="compact ? 'px-3 py-1.5' : 'grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)] gap-3 px-3 py-1.5'"
      >
        <dt :class="['font-semibold text-slate-500', compact && 'text-[11.5px]']">{{ row.icon }} {{ row.label }}</dt>
        <dd class="break-words whitespace-pre-line text-slate-800">{{ row.value }}</dd>
      </div>
    </dl>

    <!-- Onglet 2 : Compétitions de l'adhérent -->
    <div v-else class="flex flex-col gap-2 text-xs" data-testid="record-competitions-list">
      <div v-if="!memberCompetitions.length" class="text-xs text-slate-400 italic py-4 text-center">
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
          <span
            :class="[
              'rounded px-1.5 py-0.5 font-semibold',
              c.participant.statut_paiement === 'paye' ? 'bg-blue-50 text-blue-700' : 'bg-amber-50 text-amber-700',
            ]"
          >
            {{ c.participant.statut_paiement === "paye" ? "💶 Payé" : "⏳ Paiement en attente" }}
          </span>
          <span v-if="c.participant.classement" class="rounded bg-violet-50 px-1.5 py-0.5 font-bold text-violet-700">
            🏅 Rang : {{ c.participant.classement }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
