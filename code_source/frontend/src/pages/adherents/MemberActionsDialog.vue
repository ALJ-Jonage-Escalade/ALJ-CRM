<script setup lang="ts">
/* The actions of the member record, in a dialog over the Adhérents page: the e-mail (coaches and admins), the edit
   form and the payment certificate (admins). open(action) first loads what the action needs (the e-mail templates,
   once; the edit form's draft). Another member selected closes the dialog. */
import { computed, inject, ref, watch } from "vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import { dialogs } from "../../composables/dialogs";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createCommunicationsApi, type EmailTemplate } from "../../services/communications";
import { createMembersApi } from "../../services/members";
import MemberAttestation from "./MemberAttestation.vue";
import MemberEmail from "./MemberEmail.vue";
import MemberForm from "./MemberForm.vue";
import type { Member } from "./members";
import { changesOf, draftOf, type MemberDraft, type RecordAction, type RecordActions, type TarifChoice } from "./record";

const props = defineProps<{ member: Member; admin: boolean; tarifs: readonly TarifChoice[] }>();
const emit = defineEmits<{
  /** The member was changed or sent a certificate: the list is read again. */
  changed: [];
  notify: [message: string, ms?: number];
}>();

const client = inject(CLIENT_KEY)!;
const membersApi = createMembersApi(client);
const communicationsApi = createCommunicationsApi(client);

const action = ref<RecordAction | null>(null);
watch(
  () => props.member.purchase_id,
  () => (action.value = null),
);
const TITLES: Record<RecordAction, string> = {
  edit: "✏️ Modifier la fiche",
  email: "✉️ E-mail à l'adhérent",
  attestation: "📄 Attestation de paiement",
};
const dialogOpen = computed({
  get: () => action.value !== null,
  set: (open) => {
    if (!open) {
      action.value = null;
    }
  },
});

// E-mail templates, for the e-mail and the certificate, loaded once
const templates = ref<EmailTemplate[]>([]);
const clubContactEmail = ref("");
let templatesLoaded = false;
async function loadTemplates(): Promise<void> {
  if (templatesLoaded) {
    return;
  }
  templatesLoaded = true;
  try {
    const answer = await communicationsApi.emailTemplates();
    templates.value = answer.templates;
    clubContactEmail.value = answer.club_contact_email;
  } catch (e) {
    templatesLoaded = false;
    console.warn("Modèles d'e-mails :", e);
  }
}

const draft = ref<MemberDraft>(draftOf());
const saving = ref(false);

async function open(next: RecordAction): Promise<void> {
  if (next === "email" || next === "attestation") {
    await loadTemplates();
  }
  if (next === "edit") {
    draft.value = draftOf(props.member);
  }
  action.value = next;
}

function sent(message: string): void {
  emit("notify", message);
  action.value = null;
  emit("changed"); // the certificate's sent date
}

async function saveEdit(): Promise<void> {
  const member = props.member;
  const { fields, lines } = changesOf(member, draft.value);
  if (!lines.length) {
    emit("notify", "ℹ️ Aucune modification détectée.");
    action.value = null;
    return;
  }
  if (
    !(await dialogs.confirm({
      title: "Valider les modifications",
      message: `Valider les modifications pour ${member.first_name} ${member.last_name} ?\n\n• ${lines.join("\n• ")}`,
      confirmLabel: "Valider",
    }))
  ) {
    return;
  }
  saving.value = true;
  try {
    await membersApi.update({ user_id: member.user_id, purchase_id: member.purchase_id, order_ref: member.order_ref, fields });
    emit("changed");
    action.value = null;
    emit("notify", `✅ Fiche de ${member.first_name} ${member.last_name} mise à jour avec succès !`);
  } catch (e) {
    emit("notify", `❌ Échec de la mise à jour : ${errorText(e)}`, 9000);
  } finally {
    saving.value = false;
  }
}

defineExpose<RecordActions>({ open });
</script>

<template>
  <UiDialog
    v-if="action"
    v-model:open="dialogOpen"
    :title="TITLES[action]"
    :wide="action !== 'attestation'"
    :xl="action === 'attestation'"
    data-testid="record-dialog"
  >
    <MemberEmail
      v-if="action === 'email'"
      :member="member"
      :templates="templates"
      :club-contact-email="clubContactEmail"
      @sent="sent"
      @failed="(message) => emit('notify', message, 9000)"
      @cancel="action = null"
    />
    <template v-else-if="admin">
      <MemberForm
        v-if="action === 'edit'"
        v-model="draft"
        :adding="false"
        :tarifs="tarifs"
        :saving="saving"
        @save="saveEdit"
        @cancel="action = null"
      />
      <MemberAttestation
        v-else
        :member="member"
        :templates="templates"
        @sent="sent"
        @failed="(message) => emit('notify', message, 9000)"
        @cancel="action = null"
      />
    </template>
  </UiDialog>
</template>
