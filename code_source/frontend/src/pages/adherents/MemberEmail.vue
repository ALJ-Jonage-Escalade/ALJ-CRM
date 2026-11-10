<script setup lang="ts">
/* E-mail to one member from the record (coaches and admins; the server lets a coach write to known members only): a template or a free text, the variables replaced in a live preview,
   sent through /api/send-email (the server replaces the variables again and adds the signature). */
import { computed, inject, ref } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createCommunicationsApi, type EmailTemplate } from "../../services/communications";
import { looksLikeEmail } from "../../lib/email";
import type { Member } from "./members";
import { fillTemplate } from "../../lib/text";
import { memberVariables, signatureText } from "./record";
import { dialogs } from "../../composables/dialogs";

const props = defineProps<{ member: Member; templates: readonly EmailTemplate[]; clubContactEmail: string }>();
const values = computed(() => memberVariables(props.member));
const emit = defineEmits<{ sent: [message: string]; failed: [message: string]; cancel: [] }>();
const communicationsApi = createCommunicationsApi(inject(CLIENT_KEY)!);

const to = computed(() => props.member.email_primary.trim());
const canSend = computed(() => looksLikeEmail(to.value));
const templateName = ref("");
const subject = ref("");
const body = ref("");
const signature = ref(true);
const sending = ref(false);
const problem = ref("");

function useTemplate(): void {
  const t = props.templates.find((x) => x.name === templateName.value);
  if (!t) {
    return;
  }
  subject.value = t.subject;
  body.value = t.body;
}

const preview = computed(
  () =>
    `Sujet : ${fillTemplate(subject.value, values.value)}\n\n${fillTemplate(body.value, values.value)}${signature.value ? `\n\n---\n${signatureText(props.clubContactEmail)}` : ""}`,
);

async function send(): Promise<void> {
  problem.value = "";
  if (!subject.value.trim() || !body.value.trim()) {
    problem.value = "⚠️ Veuillez renseigner le sujet et le message.";
    return;
  }
  const m = props.member;
  if (
    !(await dialogs.confirm({
      title: "Envoyer l'e-mail",
      message: `Envoyer cet e-mail à ${m.first_name} ${m.last_name} <${to.value}> ?`,
      confirmLabel: "Envoyer",
    }))
  ) {
    return;
  }
  sending.value = true;
  try {
    await communicationsApi.sendEmail({
      subject: subject.value.trim(),
      body: body.value.trim(),
      add_signature: signature.value,
      recipients: [
        {
          id: m.user_id,
          first_name: m.first_name,
          last_name: m.last_name,
          email: to.value,
          num_licence: m.licence_ffme,
          tarif: m.tarif_name,
          season: m.season_name,
        },
      ],
    });
    emit("sent", `✅ E-mail envoyé avec succès à ${m.first_name} ${m.last_name} !`);
  } catch (e) {
    emit("failed", `❌ Échec d'envoi : ${errorText(e)}`);
  } finally {
    sending.value = false;
  }
}

const label = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const field = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]";
</script>

<template>
  <form novalidate class="flex flex-col gap-3" data-testid="email-form" @submit.prevent="send">
    <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <b class="text-sm text-slate-800">{{ member.first_name }} {{ member.last_name }}</b>
      <div data-testid="email-to" class="text-[12.5px] text-accent">{{ to ? `✉️ ${to}` : "Aucune adresse e-mail" }}</div>
      <p v-if="!canSend" class="mt-1 text-xs font-bold text-red-600">
        ⚠️ Cet adhérent n'a pas d'adresse e-mail valide : l'envoi est impossible.
      </p>
    </div>
    <div>
      <label for="email-template" :class="label">Modèle d'e-mail</label>
      <select id="email-template" v-model="templateName" data-testid="email-template" :class="field" @change="useTemplate">
        <option value="">-- E-mail libre / personnalisé --</option>
        <option v-for="t in templates" :key="t.name" :value="t.name">{{ t.name }}</option>
      </select>
    </div>
    <div>
      <label for="email-subject" :class="label">Sujet *</label>
      <input
        id="email-subject"
        v-model="subject"
        data-testid="email-subject"
        type="text"
        placeholder="Sujet de votre message…"
        :class="field"
      />
    </div>
    <div>
      <label for="email-body" :class="label">Message * (variables : {first_name}, {last_name}, {num_licence}, {tarif}, {season})</label>
      <textarea id="email-body" v-model="body" data-testid="email-body" rows="6" placeholder="Bonjour {first_name}, …" :class="field" />
    </div>
    <label class="flex cursor-pointer items-center gap-2 text-[12.5px] text-slate-700">
      <input v-model="signature" type="checkbox" data-testid="email-signature" class="accent-accent" />
      Ajouter la signature officielle ALJ Escalade
    </label>
    <div>
      <div :class="label">👁 Aperçu</div>
      <div
        data-testid="email-preview"
        class="max-h-40 overflow-y-auto rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-[12.5px] leading-normal whitespace-pre-wrap"
      >
        {{ preview }}
      </div>
    </div>
    <p v-if="problem" role="alert" data-testid="email-problem" class="text-xs font-bold text-red-600">{{ problem }}</p>
    <UiDialogActions>
      <UiButton variant="muted" data-testid="email-cancel" @click="emit('cancel')">Annuler</UiButton>
      <UiButton type="submit" data-testid="email-send" :disabled="!canSend" :busy="sending && 'Envoi en cours…'">🚀 Envoyer</UiButton>
    </UiDialogActions>
  </form>
</template>
