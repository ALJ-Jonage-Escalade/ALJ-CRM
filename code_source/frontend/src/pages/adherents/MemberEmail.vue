<script setup lang="ts">
/* E-mail to one member from the record (coaches and admins; the server lets a coach write to known members only): a
   member template (the default one first) or a free text, written with the variables' labels and replaced in a live preview,
   sent through /api/send-email (the server replaces the variables again and adds the signature). */
import { computed, inject, ref } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createCommunicationsApi, type EmailTemplate } from "../../services/communications";
import { looksLikeEmail } from "../../lib/email";
import type { Member } from "./members";
import { renderHtml, renderTemplate, templateError, toKeys, toLabels } from "../../lib/templateVariables";
import { initialOfKind, templatesOfKind } from "../../lib/emailTemplates";
import TemplateField from "../../components/TemplateField.vue";
import { memberVariables, signatureText } from "./record";
import { dialogs } from "../../composables/dialogs";

const props = defineProps<{ member: Member; templates: readonly EmailTemplate[]; clubContactEmail: string }>();
const values = computed(() => memberVariables(props.member));
const emit = defineEmits<{ sent: [message: string]; failed: [message: string]; cancel: [] }>();
const communicationsApi = createCommunicationsApi(inject(CLIENT_KEY)!);

const to = computed(() => props.member.email_primary.trim());
const canSend = computed(() => looksLikeEmail(to.value));
const offered = computed(() => templatesOfKind(props.templates, "adherent"));
const templateName = ref(initialOfKind(props.templates, "adherent", () => undefined)?.name ?? "");
/** Subject and body with the variables' labels ({Prénom}); sent with their keys. */
const subject = ref("");
const body = ref("");
const signature = ref(true);
const sending = ref(false);
const problem = ref("");

function useTemplate(): void {
  const t = offered.value.find((x) => x.name === templateName.value);
  if (!t) {
    return;
  }
  subject.value = toLabels(t.subject);
  body.value = toLabels(t.body);
}
useTemplate();

const previewSubject = computed(() => renderTemplate(subject.value, values.value));
const previewBody = computed(() => renderHtml(body.value, values.value));

async function send(): Promise<void> {
  problem.value = "";
  if (!subject.value.trim() || !body.value.trim()) {
    problem.value = "⚠️ Veuillez renseigner le sujet et le message.";
    return;
  }
  const unknown = templateError([subject.value, body.value], "adherent");
  if (unknown) {
    problem.value = `⚠️ ${unknown}`;
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
      subject: toKeys(subject.value.trim()),
      body: toKeys(body.value.trim()),
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
          amount: m.amount,
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
        <option v-for="t in offered" :key="t.name" :value="t.name">{{ t.name }}</option>
      </select>
    </div>
    <TemplateField id="email-subject" v-model="subject" kind="adherent" label="Sujet *" placeholder="Sujet de votre message…" />
    <TemplateField id="email-body" v-model="body" kind="adherent" label="Message *" multiline :rows="6" placeholder="Bonjour {Prénom}, …" />
    <label class="flex cursor-pointer items-center gap-2 text-[12.5px] text-slate-700">
      <input v-model="signature" type="checkbox" data-testid="email-signature" class="accent-accent" />
      Ajouter la signature officielle ALJ Escalade
    </label>
    <div>
      <div :class="label">👁 Aperçu</div>
      <div
        data-testid="email-preview"
        class="max-h-40 overflow-y-auto rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-[12.5px] leading-normal break-words"
      >
        <p class="mb-3">Sujet : {{ previewSubject }}</p>
        <!-- eslint-disable-next-line vue/no-v-html -- renderHtml escapes everything but the tags the server sends -->
        <div v-html="previewBody" />
        <p v-if="signature" class="mt-3 border-t border-slate-300 pt-2 whitespace-pre-wrap">{{ signatureText(clubContactEmail) }}</p>
      </div>
    </div>
    <p v-if="problem" role="alert" data-testid="email-problem" class="text-xs font-bold text-red-600">{{ problem }}</p>
    <UiDialogActions>
      <UiButton variant="muted" data-testid="email-cancel" @click="emit('cancel')">Annuler</UiButton>
      <UiButton type="submit" data-testid="email-send" :disabled="!canSend" :busy="sending && 'Envoi en cours…'">🚀 Envoyer</UiButton>
    </UiDialogActions>
  </form>
</template>
