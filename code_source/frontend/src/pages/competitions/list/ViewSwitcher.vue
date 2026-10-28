<script setup lang="ts">
/* Cards, table or calendar: how the competition list is shown. */
import type { ViewMode } from "./filters";

const viewMode = defineModel<ViewMode>({ required: true });

const VIEWS: { id: ViewMode; label: string }[] = [
  { id: "cards", label: "🗂️ Cartes" },
  { id: "table", label: "📋 Tableau" },
  { id: "calendar", label: "📅 Calendrier" },
];
</script>

<template>
  <div class="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 text-xs font-medium" data-testid="view-switcher">
    <button
      v-for="view in VIEWS"
      :key="view.id"
      type="button"
      :class="[
        'px-2 py-1 rounded-md cursor-pointer transition-colors',
        viewMode === view.id ? 'bg-white font-bold text-accent shadow-xs' : 'text-slate-600 hover:text-slate-900',
      ]"
      :data-testid="`view-${view.id}`"
      @click="viewMode = view.id"
    >
      {{ view.label }}
    </button>
  </div>
</template>
