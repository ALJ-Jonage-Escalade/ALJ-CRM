<script setup lang="ts">
/* Cards, table or calendar: how the competition list is shown. On a computer only: phones show the cards. */
import type { ViewMode } from "./filters";

const viewMode = defineModel<ViewMode>({ required: true });

const VIEWS: { id: ViewMode; label: string }[] = [
  { id: "cards", label: "🗂️ Cartes" },
  { id: "table", label: "📋 Tableau" },
  { id: "calendar", label: "📅 Calendrier" },
];
</script>

<template>
  <!-- Same look as the former section tabs of the page (before the sub-menu) -->
  <div class="hidden gap-1.5 overflow-x-auto md:flex" role="group" aria-label="Affichage des compétitions" data-testid="view-switcher">
    <button
      v-for="view in VIEWS"
      :key="view.id"
      type="button"
      :class="[
        'shrink-0 cursor-pointer rounded-lg px-3 py-1.5 text-[13px] font-bold',
        viewMode === view.id ? 'bg-accent text-white' : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
      ]"
      :aria-pressed="viewMode === view.id"
      :data-testid="`view-${view.id}`"
      @click="viewMode = view.id"
    >
      {{ view.label }}
    </button>
  </div>
</template>
