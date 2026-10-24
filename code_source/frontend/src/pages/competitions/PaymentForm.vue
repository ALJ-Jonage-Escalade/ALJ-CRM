<script setup lang="ts">
/* A payment received outside HelloAsso (cheque, cash): the competitor becomes selected and paid. */
import { computed, ref } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import type { Participant } from "./competitions";

const props = defineProps<{ participant: Participant; price: number; busy: boolean }>();
const emit = defineEmits<{ confirm: [amount: number]; cancel: [] }>();

const amount = ref(String(props.price || ""));
const value = computed(() => Number(amount.value.replace(",", ".")));
const invalid = ref(false);

function confirm(): void {
  invalid.value = !(value.value > 0);
  if (!invalid.value) {
    emit("confirm", value.value);
  }
}
</script>

<template>
  <form novalidate class="flex flex-col gap-3" data-testid="payment-form" @submit.prevent="confirm">
    <p class="text-[13px]">
      Paiement par chèque ou en espèces de <b>{{ participant.prenom }} {{ participant.nom }}</b
      >.
    </p>
    <div>
      <label for="payment-amount" class="mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase">Montant reçu (€)</label>
      <input
        id="payment-amount"
        v-model="amount"
        inputmode="decimal"
        data-testid="payment-amount"
        class="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-[13px]"
      />
      <p v-if="invalid" class="mt-1 text-xs font-semibold text-red-600">Indiquez un montant positif.</p>
    </div>
    <div class="flex gap-2">
      <UiButton type="submit" data-testid="payment-ok" :busy="busy && 'Enregistrement…'">💶 Enregistrer le paiement</UiButton>
      <UiButton variant="muted" @click="emit('cancel')">Annuler</UiButton>
    </div>
  </form>
</template>
