<script setup lang="ts">
/* The cards view of the competition list, with the archives on demand. */
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { period, type Competition } from "../competitions";
import CompetitionCard from "./CompetitionCard.vue";

defineProps<{
  competitions: readonly Competition[];
  archived: readonly Competition[];
  /** The list is loaded (else the page says why it is empty) */
  loaded: boolean;
  /** A filter hides competitions */
  filtered: boolean;
  selectedId: Competition["id"] | undefined;
}>();

const showArchived = ref(false);
</script>

<template>
  <ul class="flex flex-col gap-2">
    <li v-if="loaded && !competitions.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">
      {{
        filtered
          ? "Aucune compétition correspondante."
          : archived.length
            ? "Aucune compétition en cours : toutes sont archivées."
            : "Aucune compétition enregistrée."
      }}
    </li>
    <li v-for="competition in competitions" :key="competition.id">
      <CompetitionCard :competition="competition" :selected="selectedId === competition.id" />
    </li>
  </ul>
  <button
    v-if="archived.length"
    type="button"
    data-testid="toggle-archives"
    :aria-expanded="showArchived"
    class="mt-2.5 cursor-pointer rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-300"
    @click="showArchived = !showArchived"
  >
    {{ showArchived ? "🙈 Masquer les archives" : `🗂 Afficher les archives (${archived.length})` }}
  </button>
  <ul v-if="showArchived" class="mt-2 flex flex-col gap-2" data-testid="archived-list">
    <li v-for="c in archived" :key="c.id">
      <RouterLink
        :to="{ query: { id: String(c.id) } }"
        data-testid="comp-card"
        class="block rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-slate-700 no-underline hover:border-accent"
      >
        <b class="block text-[14px]" data-testid="comp-name">{{ c.nom }}</b>
        <span class="block text-xs text-slate-500">📅 {{ period(c) }} · 📦 Archivée</span>
      </RouterLink>
    </li>
  </ul>
</template>
