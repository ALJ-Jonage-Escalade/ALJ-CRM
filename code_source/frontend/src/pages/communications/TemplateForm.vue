<script setup lang="ts">
/* Edits an e-mail template: name, sender, subject and body (TemplateField: the variables' labels and the bold /
   italic / underline / link tags inserted at the cursor). Submitting checks the template first: "save" when it can be saved, else "invalid"
   with the reason. */
import type { EmailTemplate } from "../../services/communications";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import TemplateField from "../../components/TemplateField.vue";
import { templateError, type Sender } from "./editor";

/** defaultSender: what the server puts when the sender is left empty, shown as placeholder. */
defineProps<{ saving?: boolean; defaultSender: Sender; senderSuggestions: readonly string[] }>();
const emit = defineEmits<{ save: []; invalid: [message: string] }>();
/** The template being edited, its variables written with their labels. */
const draft = defineModel<EmailTemplate>({ required: true });
const signature = defineModel<boolean>("signature", { default: true });

function submit(): void {
  const error = templateError(draft.value);
  if (error) {
    emit("invalid", error);
  } else {
    emit("save");
  }
}

const INPUT = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]";
const LABEL = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
</script>

<template>
  <form novalidate class="flex flex-col gap-3.5" @submit.prevent="submit">
    <UiCard>
      <label for="template-name" :class="LABEL">Titre / Nom du modèle *</label>
      <input
        id="template-name"
        v-model="draft.name"
        type="text"
        data-testid="template-name"
        placeholder="Titre du modèle…"
        :class="[INPUT, 'font-bold text-club-blue']"
      />
    </UiCard>

    <UiCard class="flex flex-col gap-2.5">
      <h2 class="text-[15px] font-bold">✉️ Message</h2>
      <div class="grid gap-3 sm:grid-cols-[1.2fr_1fr]">
        <div>
          <label for="sender-email" :class="LABEL">Expéditeur (De) *</label>
          <input
            id="sender-email"
            v-model="draft.sender_email"
            type="email"
            list="sender-suggestions"
            data-testid="sender-email"
            :placeholder="defaultSender.sender_email"
            :class="INPUT"
          />
          <datalist id="sender-suggestions" data-testid="sender-suggestions">
            <option v-for="address in senderSuggestions" :key="address" :value="address" />
          </datalist>
        </div>
        <div>
          <label for="sender-name" :class="LABEL">Nom d'affichage</label>
          <input
            id="sender-name"
            v-model="draft.sender_name"
            type="text"
            data-testid="sender-name"
            :placeholder="defaultSender.sender_name"
            :class="INPUT"
          />
        </div>
      </div>

      <TemplateField id="subject" v-model="draft.subject" label="Objet de l'e-mail *" placeholder="Sujet de votre message…" />
      <TemplateField id="body" v-model="draft.body" label="Corps du message *" multiline placeholder="Saisissez le corps du message…" />

      <label class="flex cursor-pointer items-center gap-1.5 text-[12.5px] text-slate-700">
        <input v-model="signature" type="checkbox" data-testid="signature" class="accent-accent" />
        Ajouter la signature officielle ALJ Escalade (logos Facebook & Instagram)
      </label>

      <div class="flex justify-end">
        <UiButton type="submit" :busy="saving && 'Enregistrement…'" data-testid="template-save">💾 Enregistrer</UiButton>
      </div>
    </UiCard>
  </form>
</template>
