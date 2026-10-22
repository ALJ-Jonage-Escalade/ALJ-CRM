<script setup lang="ts">
/* Payment certificate of a membership (admins): the PDF made by the server (stamp and signature) shown in a frame,
   downloaded, or sent by e-mail with a template; the server then records the sent date. The server reads the amount,
   payer and status of the membership itself: only the purchase is sent. Nothing is kept: the PDF lives in memory while
   the pane is open. */
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import { CLIENT_KEY, errorText, unwrap } from "../../lib/client";
import { saveFile } from "../../lib/download";
import { looksLikeEmail } from "../../lib/email";
import type { Member } from "./members";
import { attestationFileName, attestationProblem, attestationRecipient, attestationTemplates, renderFor, type Template } from "./record";

const props = defineProps<{ member: Member; templates: readonly Template[] }>();
const emit = defineEmits<{ sent: [message: string]; failed: [message: string]; cancel: [] }>();
const client = inject(CLIENT_KEY)!;

const choices = computed(() => attestationTemplates(props.templates));
const templateName = ref(choices.value.initial.name);
const to = ref(attestationRecipient(props.member));
const subject = ref("");
const body = ref("");
const signature = ref(true);

function useTemplate(): void {
  const t = choices.value.list.find((x) => x.name === templateName.value) ?? choices.value.initial;
  subject.value = renderFor(t.subject, props.member);
  body.value = renderFor(t.body, props.member);
}
useTemplate();

// The PDF
const ineligible = attestationProblem(props.member);
const pdf = ref<Blob | null>(null);
const pdfUrl = ref("");
const loading = ref(!ineligible);
const loadError = ref("");

onMounted(async () => {
  if (ineligible) return;
  try {
    const blob = await unwrap(client.POST("/api/attestations/preview", {
      body: { purchase_id: props.member.purchase_id, season: props.member.season_name },
      parseAs: "blob",
    }));
    pdf.value = blob;
    pdfUrl.value = URL.createObjectURL(blob);
  } catch (e) {
    loadError.value = `❌ Erreur de génération : ${errorText(e)}`;
  } finally {
    loading.value = false;
  }
});
onBeforeUnmount(() => {
  if (pdfUrl.value) URL.revokeObjectURL(pdfUrl.value);
});

function download(): void {
  if (pdf.value) saveFile(pdf.value, attestationFileName(props.member));
}

const sending = ref(false);
const problem = ref("");
const canSend = computed(() => !!pdf.value && looksLikeEmail(to.value.trim()));

async function send(): Promise<void> {
  problem.value = "";
  const recipient = to.value.trim();
  if (!looksLikeEmail(recipient)) {
    problem.value = "⚠️ Veuillez renseigner une adresse e-mail de destination valide.";
    return;
  }
  if (!subject.value.trim() || !body.value.trim()) {
    problem.value = "⚠️ Le sujet et le corps de l'e-mail ne peuvent pas être vides.";
    return;
  }
  if (!confirm(`Envoyer l'attestation de paiement PDF à ${recipient} ?`)) return;
  sending.value = true;
  try {
    await unwrap(client.POST("/api/attestations/send", {
      body: {
        purchase_id: props.member.purchase_id, season: props.member.season_name, to_email: recipient,
        template_name: templateName.value, subject: subject.value.trim(), body: body.value.trim(), add_signature: signature.value,
      },
    }));
    emit("sent", `✅ Attestation envoyée avec succès à ${recipient} !`);
  } catch (e) {
    emit("failed", `❌ Échec d'envoi de l'attestation : ${errorText(e)}`);
  } finally {
    sending.value = false;
  }
}

const label = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const field = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]";
</script>

<template>
  <form novalidate class="flex flex-col gap-3" data-testid="attestation-form" @submit.prevent="send">
    <div class="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <div>
        <b class="text-sm text-slate-800">{{ member.first_name }} {{ member.last_name }}</b>
        <div class="text-[12.5px] text-slate-500">Payeur : {{ member.payer || "Adhérent" }}</div>
        <div v-if="member.email_sent_date" class="text-[12.5px] text-slate-500">✉️ Déjà envoyée le {{ member.email_sent_date }}</div>
      </div>
      <div class="text-base font-extrabold text-green-600">{{ member.amount ?? 0 }} €</div>
      <p v-if="ineligible" data-testid="attestation-ineligible" class="w-full text-xs font-bold text-red-600">
        ⚠️ Impossible de générer une attestation : {{ ineligible }}.
      </p>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <div class="flex flex-col gap-3">
        <div>
          <label for="attestation-template" :class="label">Modèle d'e-mail</label>
          <select id="attestation-template" v-model="templateName" data-testid="attestation-template" :class="field" @change="useTemplate">
            <option v-for="t in choices.list" :key="t.name" :value="t.name">{{ t.name }}</option>
          </select>
        </div>
        <div>
          <label for="attestation-to" :class="label">Destinataire (payeur ou adhérent) *</label>
          <input id="attestation-to" v-model="to" data-testid="attestation-to" type="email" placeholder="destinataire@example.com" :class="field">
        </div>
        <div>
          <label for="attestation-subject" :class="label">Sujet *</label>
          <input id="attestation-subject" v-model="subject" data-testid="attestation-subject" type="text" :class="field">
        </div>
        <div>
          <label for="attestation-body" :class="label">Message d'accompagnement *</label>
          <textarea id="attestation-body" v-model="body" data-testid="attestation-body" rows="7" :class="field" />
        </div>
        <label class="flex cursor-pointer items-center gap-2 text-[12.5px] text-slate-700">
          <input v-model="signature" type="checkbox" class="accent-accent">
          Ajouter la signature officielle ALJ Escalade
        </label>
      </div>
      <div class="flex min-h-80 flex-col overflow-hidden rounded-lg bg-slate-200">
        <iframe v-if="pdfUrl" :src="pdfUrl" title="Aperçu de l'attestation" data-testid="attestation-pdf" class="min-h-96 w-full flex-1 border-0" />
        <p v-else data-testid="attestation-status" class="m-auto p-5 text-center text-[13px] text-slate-500">
          {{ ineligible ? "Document non disponible pour cette inscription." : loadError || "⏳ Génération du PDF en mémoire…" }}
        </p>
      </div>
    </div>

    <p v-if="problem" role="alert" data-testid="attestation-problem" class="text-xs font-bold text-red-600">{{ problem }}</p>
    <div class="flex flex-wrap justify-end gap-2">
      <UiButton variant="muted" data-testid="attestation-cancel" @click="emit('cancel')">Fermer</UiButton>
      <UiButton variant="muted" data-testid="attestation-download" :disabled="!pdf" @click="download">📥 Télécharger le PDF</UiButton>
      <UiButton type="submit" data-testid="attestation-send" :disabled="!canSend" :busy="sending && 'Envoi en cours…'">🚀 Envoyer par e-mail</UiButton>
    </div>
  </form>
</template>
