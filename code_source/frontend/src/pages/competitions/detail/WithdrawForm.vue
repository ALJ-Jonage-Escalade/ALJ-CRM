<script setup lang="ts">
/* A competitor who paid no longer takes part: never refunded, the coach chooses what happens to the money (carried
   over to a next competition, a credit in the season balance; or lost, kept by the club), with a required comment. */
import { ref } from "vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiDialogActions from "../../../components/ui/UiDialogActions.vue";
import { formatEuros } from "../../../lib/format";
import { type Participant } from "../competitions";

defineProps<{ participant: Participant; busy: boolean }>();
const emit = defineEmits<{ confirm: [mode: "reporte" | "perdu", note: string]; cancel: [] }>();

const mode = ref<"reporte" | "perdu">("reporte");
const note = ref("");
const missing = ref(false);

function confirm(): void {
  missing.value = !note.value.trim();
  if (!missing.value) {
    emit("confirm", mode.value, note.value.trim());
  }
}
</script>

<template>
  <form novalidate class="flex flex-col gap-3" data-testid="withdraw-form" @submit.prevent="confirm">
    <p class="text-[13px] leading-normal" data-testid="withdraw-text">
      <b>{{ participant.nom }} {{ participant.prenom }}</b>
      a payé
      <b>{{ formatEuros(participant.montant_paye) }}</b>
      <template v-if="participant.commande_helloasso">(commande {{ participant.commande_helloasso }})</template>
      mais ne participe plus. Aucun remboursement : choisissez le sort de cet argent.
    </p>
    <label class="flex cursor-pointer items-start gap-2 text-[13px]">
      <input v-model="mode" type="radio" value="reporte" data-testid="withdraw-reporte" class="mt-0.5" />
      <span>
        <b>🔄 Report</b>
        : l'argent reste un crédit pour sa prochaine épreuve (bilan de la saison).
      </span>
    </label>
    <label class="flex cursor-pointer items-start gap-2 text-[13px]">
      <input v-model="mode" type="radio" value="perdu" data-testid="withdraw-perdu" class="mt-0.5" />
      <span>
        <b>🚫 Perdu</b>
        : les frais restent acquis au club ou à l'organisateur.
      </span>
    </label>
    <div>
      <label for="withdraw-note" class="mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase">Commentaire (motif) *</label>
      <textarea
        id="withdraw-note"
        v-model="note"
        rows="2"
        data-testid="withdraw-note"
        class="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-[13px]"
      />
      <p v-if="missing" class="mt-1 text-xs font-semibold text-red-600" data-testid="withdraw-error">
        Un commentaire est obligatoire pour expliquer le désistement.
      </p>
    </div>
    <UiDialogActions>
      <UiButton variant="muted" data-testid="withdraw-cancel" @click="emit('cancel')">Annuler</UiButton>
      <UiButton type="submit" data-testid="withdraw-ok" :busy="busy && 'Enregistrement…'">Valider le désistement</UiButton>
    </UiDialogActions>
  </form>
</template>
