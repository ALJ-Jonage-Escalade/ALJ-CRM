<script setup lang="ts">
/* Edits an e-mail template: name, sender, subject and body (TemplateField: the variables' labels and the bold /
   italic / underline / link tags inserted at the cursor). Submitting checks the template first: "save" when it can be saved, else "invalid"
   with the reason. */
import type { EmailTemplate } from "../../services/communications";
import { computed, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import TemplateField from "../../components/TemplateField.vue";
import { KIND_LABELS, type TemplateKind } from "../../lib/templateVariables";
import { templateError, type Sender } from "./editor";

/** defaultSender: the sending account (used when the sender is left empty) and the club's name; senderAliases: every
    address an e-mail may leave from, the account first; aliasesError: why only the account is listed; saved: the
    template as the server has it (none for a template being created). */
const props = defineProps<{
  saving?: boolean;
  defaultSender: Sender;
  senderAliases: readonly string[];
  aliasesError?: string;
  saved?: EmailTemplate;
}>();
const emit = defineEmits<{ save: []; invalid: [message: string] }>();
/** The template being edited, its variables written with their labels. */
const draft = defineModel<EmailTemplate>({ required: true });
const signature = defineModel<boolean>("signature", { default: true });
const KINDS = Object.entries(KIND_LABELS) as [TemplateKind, string][];

/** A default template moved to another kind is no longer a default (the server drops the mark too). */
const defaultDropped = computed(() => Boolean(props.saved?.is_default) && draft.value.kind !== props.saved?.kind);
watch(
  () => draft.value.kind,
  () => {
    if (props.saved?.is_default) {
      draft.value.is_default = !defaultDropped.value;
    }
  },
);

const sameAddress = (a: string, b: string): boolean => a.trim().toLowerCase() === b.trim().toLowerCase();
/** The sender may be used: empty (the account), the account or one of its aliases. */
const senderAllowed = computed(
  () => !draft.value.sender_email.trim() || props.senderAliases.some((a) => sameAddress(a, draft.value.sender_email)),
);
/** The addresses offered after the default: the aliases, and the saved sender when it is not one of them (flagged). */
const senderChoices = computed(() => {
  const aliases = props.senderAliases.filter((address) => !sameAddress(address, props.defaultSender.sender_email));
  const current = draft.value.sender_email;
  return current && !aliases.some((address) => address === current) ? [...aliases, current] : aliases;
});

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
      <div class="mt-2.5 grid gap-3 sm:grid-cols-[1fr_1.2fr]">
        <div>
          <label for="template-kind" :class="LABEL">Type de modèle</label>
          <select id="template-kind" v-model="draft.kind" data-testid="template-kind" :class="INPUT">
            <option v-for="[kind, label] in KINDS" :key="kind" :value="kind">{{ label }}</option>
          </select>
        </div>
        <div class="self-end">
          <label class="flex cursor-pointer items-center gap-1.5 text-[12.5px] text-slate-700">
            <input v-model="draft.is_default" type="checkbox" data-testid="template-default" class="accent-accent" />
            Modèle par défaut pour ce type
          </label>
          <p v-if="defaultDropped" data-testid="template-default-dropped" class="mt-0.5 text-xs text-amber-700">
            Avec ce type, il n'est plus le modèle par défaut de son ancien type.
          </p>
        </div>
        <p v-if="draft.needs_fixing" data-testid="template-needs-fixing" class="self-end text-xs font-semibold text-amber-700">
          ⚠️ À corriger : ce modèle contient une variable ancienne ou non disponible pour son type. Vérifiez-le puis enregistrez-le.
        </p>
      </div>
    </UiCard>

    <UiCard class="flex flex-col gap-2.5">
      <h2 class="text-[15px] font-bold">✉️ Message</h2>
      <div class="grid gap-3 sm:grid-cols-[1.2fr_1fr]">
        <div>
          <label for="sender-email" :class="LABEL">Expéditeur (De) *</label>
          <select id="sender-email" v-model="draft.sender_email" data-testid="sender-email" :class="INPUT">
            <option value="">Par défaut ({{ defaultSender.sender_email }})</option>
            <option v-for="address in senderChoices" :key="address" :value="address">{{ address }}</option>
          </select>
          <p v-if="!senderAllowed" data-testid="sender-not-allowed" class="mt-0.5 text-xs font-semibold text-amber-700">
            ⚠️ Cette adresse n'est pas un alias d'envoi du compte {{ defaultSender.sender_email }} : les envois de ce modèle sont refusés.
            Choisissez-en une autre, ou ajoutez-la comme alias dans Gmail.
          </p>
          <p v-if="aliasesError" data-testid="sender-aliases-error" class="mt-0.5 text-xs text-amber-700">
            Seul le compte d'envoi est proposé : {{ aliasesError }}
          </p>
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

      <TemplateField
        id="subject"
        v-model="draft.subject"
        :kind="draft.kind"
        label="Objet de l'e-mail *"
        placeholder="Sujet de votre message…"
      />
      <TemplateField
        id="body"
        v-model="draft.body"
        :kind="draft.kind"
        label="Corps du message *"
        multiline
        placeholder="Saisissez le corps du message…"
      />

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
