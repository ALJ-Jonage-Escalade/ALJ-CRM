<script setup lang="ts">
/* The "De" (from) of a send screen: a template's sender, read-only (its own, else the sending account), flagged when
   the server no longer allows it; for a free text, a choice among the account and its aliases (empty: the account). */
import { computed } from "vue";
import type { EmailTemplate } from "../services/communications";

const props = defineProps<{ template?: EmailTemplate; account: string; aliases: readonly string[] }>();
/** The address chosen for a free text; empty: the sending account. */
const sender = defineModel<string>({ required: true });

const accountText = computed(() => props.account || "compte d'envoi");
const others = computed(() => props.aliases.filter((address) => address.toLowerCase() !== props.account.toLowerCase()));
</script>

<template>
  <div>
    <template v-if="template">
      <p data-testid="email-from" class="text-[12.5px] text-slate-600">De : {{ template.sender_email || accountText }}</p>
      <p v-if="template.sender_allowed === false" data-testid="email-sender-not-allowed" class="text-xs font-bold text-amber-700">
        ⚠️ L'expéditeur de ce modèle n'est pas un alias d'envoi autorisé : modifiez le modèle (Communications › Modèles) ou passez en saisie
        libre.
      </p>
    </template>
    <template v-else>
      <label for="email-sender" class="mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase">De</label>
      <select
        id="email-sender"
        v-model="sender"
        data-testid="email-sender"
        class="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]"
      >
        <option value="">Par défaut ({{ accountText }})</option>
        <option v-for="address in others" :key="address" :value="address">{{ address }}</option>
      </select>
    </template>
  </div>
</template>
