<script setup lang="ts">
/* Season, search and date chips above the competition list (the calendar keeps the search only). */
import type { When } from "../competitions";

defineProps<{
  seasons: readonly string[];
  calendar: boolean;
}>();
const selectedSeason = defineModel<string>("season", { required: true });
const search = defineModel<string>("search", { required: true });
const when = defineModel<When>("when", { required: true });

const WHEN: { id: When; label: string }[] = [
  { id: "all", label: "Toutes" },
  { id: "upcoming", label: "À venir" },
  { id: "past", label: "Passées" },
];

const chip = (active: boolean) => [
  "cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold",
  active ? "border-accent bg-accent text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
];
</script>

<template>
  <div v-if="!calendar" class="mb-2.5 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
    <div class="flex items-center gap-1.5 text-xs">
      <span class="font-semibold text-slate-500">Saison :</span>
      <select
        v-model="selectedSeason"
        data-testid="comp-season-filter"
        class="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700"
      >
        <option value="all">Toutes les saisons</option>
        <option v-for="s in seasons" :key="s" :value="s">{{ s }}</option>
      </select>
    </div>
  </div>

  <div class="flex flex-wrap items-center gap-1.5 mb-2">
    <input
      v-model="search"
      type="search"
      data-testid="comp-search"
      placeholder="Rechercher (nom, lieu, discipline)…"
      class="min-w-32 flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px] md:basis-full"
    />
    <div v-if="!calendar" class="flex pt-1 gap-2">
      <button
        v-for="w in WHEN"
        :key="w.id"
        type="button"
        :data-testid="`when-${w.id}`"
        :aria-pressed="when === w.id"
        :class="chip(when === w.id)"
        @click="when = w.id"
      >
        {{ w.label }}
      </button>
    </div>
  </div>
</template>
