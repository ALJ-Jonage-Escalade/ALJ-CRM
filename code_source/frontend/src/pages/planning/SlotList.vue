<script setup lang="ts">
/* Table view of the slots: columns on a wide screen, one card per slot on a phone, with edit and delete buttons. */
import UiBadge from "../../components/ui/UiBadge.vue";
import type { BadgeColor } from "../../components/ui/palette";
import { slotKind, type Kind, type Slot } from "./slots";

defineProps<{ slots: readonly Slot[] }>();
const emit = defineEmits<{ edit: [slot: Slot]; remove: [slot: Slot] }>();

const KIND_COLOR: Record<Kind, BadgeColor> = {
  competition: "green",
  perfectionnement: "pink",
  cours: "indigo",
  "autonome-bloc": "orange",
  autonome: "slate",
};

const COLUMNS = "md:grid md:grid-cols-[120px_minmax(0,1.3fr)_110px_76px_minmax(0,1fr)_minmax(0,1.3fr)_40px_84px] md:items-start md:gap-3";
</script>

<template>
  <div class="rounded-xl border border-slate-200 bg-white text-[12.5px] shadow-sm">
    <div :class="['hidden border-b border-slate-200 bg-slate-50 px-3 py-2 font-bold', COLUMNS]" aria-hidden="true">
      <span>Jour & horaires</span>
      <span>Groupe & catégorie</span>
      <span>Type</span>
      <span class="text-center">Séance autonome</span>
      <span>Encadrant(s)</span>
      <span>Tarif(s) HelloAsso</span>
      <span class="text-center">WA</span>
      <span class="text-center">Actions</span>
    </div>
    <ul v-if="slots.length">
      <li
        v-for="slot in slots"
        :key="slot.id"
        data-testid="slot-row"
        :class="['flex flex-col gap-1.5 border-b border-slate-100 px-3 py-2.5 last:border-b-0', COLUMNS]"
      >
        <div class="font-semibold">
          <div>{{ slot.jour || "—" }}</div>
          <div class="text-[11px] font-normal text-slate-500">🕒 {{ slot.horaires || "—" }}</div>
        </div>
        <div class="min-w-0">
          <b>{{ slot.groupe }}</b>
          <div v-if="slot.categorie_age" class="text-[11.5px] text-slate-500">Catégorie : {{ slot.categorie_age }}</div>
          <div v-if="slot.naissance_min || slot.naissance_max" class="text-[10.5px] text-slate-500">
            Nés entre {{ slot.naissance_min || "…" }} et {{ slot.naissance_max || "…" }}
          </div>
        </div>
        <div>
          <UiBadge :color="KIND_COLOR[slotKind(slot)]" variant="soft">{{ slot.type || "cours" }}</UiBadge>
        </div>
        <div data-testid="slot-seance-autonome-cell" class="md:text-center">
          <span v-if="slot.seance_autonome" title="Sur la fiche de présence autonome">
            ✅
            <span class="text-xs md:sr-only">Séance autonome</span>
          </span>
          <span v-else class="hidden text-[11px] text-slate-500 md:inline">—</span>
        </div>
        <div class="text-xs">
          <span class="text-slate-500 md:hidden">👤</span>
          {{ slot.encadrants.join(", ") || "—" }}
        </div>
        <div class="flex flex-wrap gap-1">
          <span v-for="tarif in slot.helloasso_tarifs" :key="tarif" class="rounded bg-slate-100 px-1.5 py-0.5 text-[11px]">
            {{ tarif }}
          </span>
          <span v-if="!slot.helloasso_tarifs.length" class="text-slate-500">Aucun tarif lié</span>
        </div>
        <div class="md:text-center">
          <a
            v-if="slot.whatsapp_link"
            :href="slot.whatsapp_link"
            target="_blank"
            rel="noopener"
            title="Ouvrir le groupe WhatsApp"
            class="no-underline"
          >
            🟢
            <span class="md:sr-only">Groupe WhatsApp</span>
          </a>
          <span v-else class="hidden text-[11px] text-slate-500 md:inline">—</span>
        </div>
        <div class="flex gap-1.5 md:justify-center">
          <button
            type="button"
            data-testid="slot-edit"
            :aria-label="`Modifier ${slot.groupe}`"
            title="Modifier"
            class="cursor-pointer rounded-lg bg-slate-200 px-2 py-1 hover:bg-slate-300"
            @click="emit('edit', slot)"
          >
            ✏️
          </button>
          <button
            type="button"
            data-testid="slot-delete"
            :aria-label="`Supprimer ${slot.groupe}`"
            title="Supprimer"
            class="cursor-pointer rounded-lg bg-slate-200 px-2 py-1 text-red-600 hover:bg-slate-300"
            @click="emit('remove', slot)"
          >
            🗑️
          </button>
        </div>
      </li>
    </ul>
    <p v-else class="px-3 py-5 text-center text-slate-500">Aucun créneau correspondant.</p>
  </div>
</template>
