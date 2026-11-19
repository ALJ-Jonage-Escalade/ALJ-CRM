<script setup lang="ts">
/* Planning › Tableau des créneaux: every slot in a table, filtered by text and kind. */
import { computed, inject, ref } from "vue";
import UiCard from "../../components/ui/UiCard.vue";
import { PLANNING_KEY } from "./context";
import SlotList from "./SlotList.vue";
import { filterSlots, KINDS, type KindFilter } from "./slots";

const { slots, open, remove } = inject(PLANNING_KEY)!;

const search = ref("");
const kind = ref<KindFilter>("all");
const shown = computed(() => filterSlots(slots.value, search.value, kind.value));

const chip = (active: boolean) => [
  "cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold",
  active ? "border-accent bg-accent text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
];
</script>

<template>
  <div class="flex flex-col gap-2.5">
    <UiCard class="flex flex-wrap items-center gap-2">
      <input
        v-model="search"
        type="search"
        data-testid="slot-search"
        aria-label="Filtrer les créneaux"
        placeholder="🔍 Filtrer les créneaux (nom, jour, encadrant, tarif)…"
        class="min-w-0 flex-1 basis-60 rounded-lg border border-slate-300 px-2.5 py-1.5 text-[12.5px]"
      />
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="[value, label] in KINDS"
          :key="value"
          type="button"
          :data-testid="`kind-${value}`"
          :aria-pressed="kind === value"
          :class="chip(kind === value)"
          @click="kind = value"
        >
          {{ label }}
        </button>
      </div>
    </UiCard>
    <SlotList :slots="shown" @edit="open" @remove="remove" />
  </div>
</template>
