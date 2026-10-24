<script setup lang="ts">
/* Read view of a member record: status, slot, every known field, call / write links. Coaches and admins can send an
   e-mail; admins also get the payment certificate and the edit form, which the page opens in a dialog. compact: a narrow
   column (the page's side panel), each label above its value. */
import { computed } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import { telHref, type Member } from "./members";
import { recordRows } from "./record";

const props = defineProps<{ member: Member; admin: boolean; compact?: boolean }>();
const emit = defineEmits<{ email: []; attestation: []; edit: [] }>();
const rows = computed(() => recordRows(props.member));
</script>

<template>
  <div data-testid="member-record-view" class="flex flex-col gap-3">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div class="flex min-w-0 flex-1 flex-col gap-3">
        <div class="flex flex-row items-start justify-between gap-2 text-lg font-bold text-slate-800">
          <div data-testid="record-name">{{ member.first_name }} {{ member.last_name }}</div>
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
        <UiButton variant="muted" small data-testid="record-attestation" title="Attestation de paiement (PDF)" @click="emit('attestation')"
          >📄 Attestation</UiButton
        >
        <UiButton
          variant="muted"
          small
          data-testid="record-edit"
          title="Modifier le créneau, les badges et les coordonnées"
          @click="emit('edit')"
          >✏️ Modifier</UiButton
        >
      </template>
      <span v-else data-testid="record-readonly" class="self-center text-[11.5px] text-slate-500 italic"
        >👁️ Modification et attestation réservées aux administrateurs</span
      >
    </div>
    <div class="flex flex-wrap gap-2">
      <a
        v-if="member.phone"
        :href="telHref(member.phone)"
        class="rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 no-underline"
        >📞 Appeler</a
      >
      <a
        v-if="member.email_primary"
        :href="`mailto:${member.email_primary}`"
        class="rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 no-underline"
        >✉️ Écrire</a
      >
    </div>

    <dl data-testid="record-fields" class="divide-y divide-slate-100 rounded-lg border border-slate-200 text-[12.5px]">
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
  </div>
</template>
