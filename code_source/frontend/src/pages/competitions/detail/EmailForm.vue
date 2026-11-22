<script setup lang="ts">
/* E-mail to the competitors of a competition (coaches and admins): the audience (a recipient can be taken out), a
   competition template of the club (its default first) or a free text, written with the variables' labels, a preview
   for the first recipient, then POST /api/send-email: the server
   replaces the variables for each one and adds the signature. */
import { computed, inject, ref, watch } from "vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiDialogActions from "../../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText } from "../../../lib/client";
import { createCommunicationsApi, type EmailTemplate } from "../../../services/communications";
import type { Competition, Row } from "../competitions";
import { audience, AUDIENCES, defaultTemplate, hasEmail, sendBody, sentMessage, variables, type Audience } from "./email";
import { plural } from "../../../lib/text";
import { renderTemplate, templateError, toKeys, toLabels } from "../../../lib/templateVariables";
import { initialOfKind, templatesOfKind } from "../../../lib/emailTemplates";
import TemplateField from "../../../components/TemplateField.vue";
import { dialogs } from "../../../composables/dialogs";

const props = defineProps<{ competition: Competition; rows: readonly Row[] }>();
const emit = defineEmits<{ sent: [message: string]; cancel: [] }>();
const communicationsApi = createCommunicationsApi(inject(CLIENT_KEY)!);

const who = ref<Audience>("selected");
const removed = ref(new Set<number | null | undefined>());
const recipients = computed(() => audience(props.rows, who.value).filter((r) => !removed.value.has(r.adherent_id)));
const reachable = computed(() => recipients.value.filter(hasEmail));
watch(who, () => (removed.value = new Set()));

/** The club's competition templates. */
const templates = ref<EmailTemplate[]>([]);
const templateName = ref("");
/** Subject and body with the variables' labels ({Prénom}); sent with their keys. */
const subject = ref("");
const body = ref("");
const sending = ref(false);
const problem = ref("");
const notConfigured = ref(false);

function useTemplate(): void {
  const t = templates.value.find((x) => x.name === templateName.value);
  if (t) {
    [subject.value, body.value] = [toLabels(t.subject), toLabels(t.body)];
  }
}

void (async () => {
  try {
    const all = (await communicationsApi.emailTemplates()).templates;
    templates.value = templatesOfKind(all, "competition");
    // On a slow network the user may have started writing: the default template must not replace their text
    if (!subject.value.trim() && !body.value.trim()) {
      templateName.value = initialOfKind(all, "competition", defaultTemplate)?.name ?? "";
      useTemplate();
    }
  } catch {
    problem.value = "⚠️ Modèles d'e-mails indisponibles : saisissez le message.";
  }
  try {
    notConfigured.value = !(await communicationsApi.emailStatus()).configured;
  } catch {
    // checked again by the server when sending
  }
})();

const preview = computed(() => {
  const first = reachable.value[0];
  if (!first) {
    return "";
  }
  const values = variables(props.competition, first);
  return `Sujet : ${renderTemplate(subject.value, values)}\n\n${renderTemplate(body.value, values)}`;
});

function take(id: number | null | undefined): void {
  removed.value = new Set([...removed.value, id]);
}

async function send(): Promise<void> {
  problem.value = "";
  if (!subject.value.trim() || !body.value.trim()) {
    problem.value = "⚠️ Veuillez renseigner le sujet et le message.";
    return;
  }
  const unknown = templateError([subject.value, body.value], "competition");
  if (unknown) {
    problem.value = `⚠️ ${unknown}`;
    return;
  }
  const n = reachable.value.length;
  if (!n) {
    problem.value = "⚠️ Aucun destinataire n'a d'adresse e-mail valide.";
    return;
  }
  if (
    !(await dialogs.confirm({
      title: "Envoyer l'e-mail",
      message: `Envoyer cet e-mail à ${n} compétiteur${plural(n)} ?`,
      confirmLabel: "Envoyer",
    }))
  ) {
    return;
  }
  sending.value = true;
  try {
    const result = await communicationsApi.sendEmail(
      sendBody(props.competition, reachable.value, toKeys(subject.value), toKeys(body.value)),
    );
    // A refused request (400) or a sending where every e-mail failed (502) is thrown by unwrap(), caught below
    emit("sent", sentMessage(result));
  } catch (e) {
    problem.value = `❌ Échec d'envoi : ${errorText(e)}`;
  } finally {
    sending.value = false;
  }
}

const label = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const field = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]";
</script>

<template>
  <form novalidate class="flex flex-col gap-3" data-testid="email-form" @submit.prevent="send">
    <p v-if="notConfigured" class="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
      ⚠️ Envoi d'e-mails non configuré sur le serveur (identifiants Gmail ou SMTP manquants).
    </p>
    <fieldset>
      <legend :class="label">Destinataires</legend>
      <label v-for="a in AUDIENCES" :key="a.id" class="mr-3 inline-flex cursor-pointer items-center gap-1.5 text-[13px]">
        <input v-model="who" type="radio" :value="a.id" :data-testid="`email-audience-${a.id}`" />
        {{ a.label }} ({{ audience(rows, a.id).length }})
      </label>
    </fieldset>
    <div
      class="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-2"
      data-testid="email-recipients"
    >
      <span v-if="!recipients.length" class="text-xs text-slate-500">Aucun destinataire.</span>
      <span
        v-for="r in recipients"
        :key="r.adherent_id ?? r.nom"
        :class="[
          'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11.5px]',
          hasEmail(r) ? 'border-slate-300 bg-white' : 'border-red-200 bg-red-50 text-red-600',
        ]"
      >
        {{ r.prenom }} {{ r.nom }} &lt;{{ r.email || "sans e-mail" }}&gt;
        <button
          type="button"
          class="cursor-pointer text-slate-400 hover:text-slate-700"
          :aria-label="`Retirer ${r.prenom} ${r.nom}`"
          @click="take(r.adherent_id)"
        >
          ✕
        </button>
      </span>
    </div>
    <p class="text-xs text-slate-500" data-testid="email-count">
      {{ reachable.length }} destinataire{{ plural(reachable.length) }} avec une adresse e-mail
    </p>
    <div>
      <label for="ce-template" :class="label">Modèle d'e-mail</label>
      <select id="ce-template" v-model="templateName" data-testid="email-template" :class="field" @change="useTemplate">
        <option value="">— Saisie libre —</option>
        <option v-for="t in templates" :key="t.name" :value="t.name">{{ t.name }}</option>
      </select>
    </div>
    <TemplateField
      id="email-subject"
      v-model="subject"
      kind="competition"
      label="Objet"
      placeholder="ex. Convocation — Championnat de bloc"
    />
    <TemplateField
      id="email-body"
      v-model="body"
      kind="competition"
      label="Message"
      multiline
      :rows="7"
      placeholder="Rédigez votre message…"
    />
    <div v-if="preview">
      <span :class="label">Aperçu pour {{ reachable[0]!.prenom }} {{ reachable[0]!.nom }}</span>
      <pre
        class="max-h-48 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-2.5 font-sans text-xs whitespace-pre-wrap"
        data-testid="email-preview"
        >{{ preview }}</pre>
    </div>
    <p v-if="problem" role="alert" class="text-[13px] font-semibold text-red-700" data-testid="email-problem">{{ problem }}</p>
    <UiDialogActions>
      <UiButton variant="muted" @click="emit('cancel')">Annuler</UiButton>
      <UiButton type="submit" data-testid="email-send" :busy="sending && 'Envoi en cours…'">🚀 Envoyer ({{ reachable.length }})</UiButton>
    </UiDialogActions>
  </form>
</template>
