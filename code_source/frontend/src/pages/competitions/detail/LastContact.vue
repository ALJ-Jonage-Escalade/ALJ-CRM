<script setup lang="ts">
/* A last-contact date (the competition's header, a competitor's row): opens the e-mail history when there is one. */
import { dayOf, type ContactState } from "./emailHistory";

defineProps<{ state: ContactState; online: boolean }>();
const emit = defineEmits<{ open: [] }>();
const link = "cursor-pointer font-semibold whitespace-nowrap hover:underline";
</script>

<template>
  <button
    v-if="state.kind === 'date'"
    type="button"
    data-testid="last-contact"
    :class="[link, 'text-blue-700']"
    title="Voir l'historique des e-mails"
    @click="emit('open')"
  >
    📧 {{ dayOf(state.at) }}
  </button>
  <button
    v-else-if="state.kind === 'failed'"
    type="button"
    data-testid="last-contact"
    :class="[link, 'text-red-600']"
    title="Le dernier e-mail n'est pas parti : voir l'historique"
    @click="emit('open')"
  >
    📧 échec
  </button>
  <span v-else-if="state.kind === 'none'" data-testid="last-contact" class="text-slate-400" title="Aucun e-mail envoyé">—</span>
  <span v-else-if="state.kind === 'unavailable'" data-testid="last-contact" class="text-slate-400 italic">
    {{ online ? "historique indisponible" : "historique indisponible hors ligne" }}
  </span>
</template>
