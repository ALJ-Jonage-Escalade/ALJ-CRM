<script setup lang="ts">
/* E-mail to the competitors of a competition (coaches and admins): the audience (a recipient can be taken out), a
   template of the club or a free text, a preview for the first recipient, then POST /api/send-email: the server
   replaces the variables for each one and adds the signature. */
import { computed, inject, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createCommunicationsApi } from "../../services/communications";
import type { Competition, Row } from "./competitions";
import { audience, AUDIENCES, defaultTemplate, hasEmail, render, sendBody, variables, type Audience, type Template } from "./email";
import { plural } from "../../lib/text";

const props = defineProps<{ competition: Competition; rows: readonly Row[] }>();
const emit = defineEmits<{ sent: [message: string]; cancel: [] }>();
const communicationsApi = createCommunicationsApi(inject(CLIENT_KEY)!);

const who = ref<Audience>("selected");
const removed = ref(new Set<number | null | undefined>());
const recipients = computed(() => audience(props.rows, who.value).filter((r) => !removed.value.has(r.adherent_id)));
const reachable = computed(() => recipients.value.filter(hasEmail));
watch(who, () => (removed.value = new Set()));

const templates = ref<Template[]>([]);
const templateName = ref("");
const subject = ref("");
const body = ref("");
const sending = ref(false);
const problem = ref("");
const notConfigured = ref(false);

function useTemplate(): void {
  const t = templates.value.find((x) => x.name === templateName.value);
  if (t) {
    [subject.value, body.value] = [t.subject, t.body];
  }
}

void (async () => {
  try {
    templates.value = (await communicationsApi.emailTemplates()).templates;
    templateName.value = defaultTemplate(templates.value)?.name ?? "";
    useTemplate();
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
  return `Sujet : ${render(subject.value, values)}\n\n${render(body.value, values)}`;
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
  const n = reachable.value.length;
  if (!n) {
    problem.value = "⚠️ Aucun destinataire n'a d'adresse e-mail valide.";
    return;
  }
  if (!confirm(`Envoyer cet e-mail à ${n} compétiteur${plural(n)} ?`)) {
    return;
  }
  sending.value = true;
  try {
    const result = await communicationsApi.sendEmail(sendBody(props.competition, reachable.value, subject.value, body.value));
    if (result.status === "error") {
      problem.value = `❌ Échec d'envoi : ${result.message || result.details?.[0]?.error || "erreur d'envoi."}`;
    } else {
      emit(
        "sent",
        `✅ ${result.sent_count} e-mail(s) envoyé(s) avec succès${result.errors_count ? `, ${result.errors_count} en échec` : ""}.`,
      );
    }
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
    <div>
      <label for="ce-subject" :class="label">Sujet</label>
      <input id="ce-subject" v-model="subject" data-testid="email-subject" :class="field" />
    </div>
    <div>
      <label for="ce-body" :class="label">Message</label>
      <textarea id="ce-body" v-model="body" rows="7" data-testid="email-body" :class="field" />
      <p class="mt-1 text-[11px] text-slate-500">
        Variables : {first_name} {last_name} {num_licence} {name_competition} {no_competition} {date_competition} {montant_competition}
        {bloc_whatsapp}
      </p>
    </div>
    <div v-if="preview">
      <span :class="label">Aperçu pour {{ reachable[0]!.prenom }} {{ reachable[0]!.nom }}</span>
      <pre
        class="max-h-48 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-2.5 font-sans text-xs whitespace-pre-wrap"
        data-testid="email-preview"
        >{{ preview }}</pre>
    </div>
    <p v-if="problem" role="alert" class="text-[13px] font-semibold text-red-700" data-testid="email-problem">{{ problem }}</p>
    <div class="flex gap-2">
      <UiButton type="submit" data-testid="email-send" :busy="sending && 'Envoi en cours…'">🚀 Envoyer ({{ reachable.length }})</UiButton>
      <UiButton variant="muted" @click="emit('cancel')">Annuler</UiButton>
    </div>
  </form>
</template>
