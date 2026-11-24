<script setup lang="ts">
/* Communications › Modèles (admins): the e-mail templates used by the Adhérents and Compétitions pages (create, edit, rename,
   delete) with a live preview, and the WhatsApp invitation text. Online only: nothing is kept on the device. */
import { computed, inject, onMounted, ref } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import UiCard from "../../components/ui/UiCard.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import UiToast from "../../components/ui/UiToast.vue";
import { useToast } from "../../composables/toast";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createCommunicationsApi, type EmailTemplate } from "../../services/communications";
import { KIND_LABELS, toKeys, toLabels, type TemplateKind } from "../../lib/templateVariables";
import EmailPreview from "./EmailPreview.vue";
import { initialTemplate, newNameError, newTemplate, preview, type Sender } from "./editor";
import TemplateForm from "./TemplateForm.vue";
import { dialogs } from "../../composables/dialogs";

const communicationsApi = createCommunicationsApi(inject(CLIENT_KEY)!);
const toast = useToast();

// E-mail templates
const templates = ref<EmailTemplate[]>([]);
const loaded = ref(false);
const loadError = ref("");
/** Saved name of the template being edited (the server renames it when the title changes). */
const selected = ref("");
const draft = ref<EmailTemplate | null>(null);
const signature = ref(true);
const saving = ref(false);
/** The default sender (the sending account), the addresses an e-mail may leave from and why that list is partial. */
const defaultSender = ref<Sender>({ sender_email: "", sender_name: "" });
const senderAliases = ref<string[]>([]);
const aliasesError = ref("");
const shown = computed(() => (draft.value ? preview(draft.value, defaultSender.value) : null));
/** A template in the list: its name, then whether it is its kind's default, needs fixing or has a sender it may not use. */
function optionText(template: EmailTemplate): string {
  return [
    template.name,
    template.is_default && "★ par défaut",
    template.needs_fixing && "⚠️ à corriger",
    template.sender_allowed === false && "⚠️ expéditeur non autorisé",
  ]
    .filter(Boolean)
    .join(" ");
}
/** The templates by kind, in the order of the kinds. */
const groups = computed(() =>
  (Object.entries(KIND_LABELS) as [TemplateKind, string][])
    .map(([kind, label]) => ({ kind, label, templates: templates.value.filter((t) => t.kind === kind) }))
    .filter((group) => group.templates.length),
);

function select(template: EmailTemplate | undefined): void {
  selected.value = template?.name ?? "";
  // Edited with the variables' labels ({Prénom}); saved with their keys
  draft.value = template ? { ...template, subject: toLabels(template.subject), body: toLabels(template.body) } : null;
}

async function loadTemplates(wanted?: string): Promise<void> {
  try {
    const answer = await communicationsApi.emailTemplates();
    templates.value = answer.templates;
    defaultSender.value = { sender_email: answer.default_sender_email, sender_name: answer.default_sender_name };
    senderAliases.value = answer.sender_aliases;
    aliasesError.value = answer.sender_aliases_error ?? "";
    loadError.value = "";
    select(initialTemplate(templates.value, wanted));
  } catch (e) {
    loadError.value = errorText(e);
    toast.show(`❌ Erreur de chargement des modèles : ${errorText(e)}`);
  } finally {
    loaded.value = true;
  }
}

function onSelect(event: Event): void {
  const name = (event.target as HTMLSelectElement).value;
  select(templates.value.find((t) => t.name === name));
}

async function save(): Promise<void> {
  // needs_fixing and sender_allowed are told by the server, not saved
  const { name, subject, body, sender_email, sender_name, kind, is_default } = draft.value!;
  saving.value = true;
  try {
    const saved = await communicationsApi.saveEmailTemplate({
      name,
      sender_email,
      sender_name,
      kind,
      is_default,
      subject: toKeys(subject),
      body: toKeys(body),
      old_name: selected.value,
    });
    toast.show(`💾 Modèle « ${saved.template.name} » enregistré avec succès !`);
    await loadTemplates(saved.template.name);
  } catch (e) {
    toast.show(`❌ Erreur d'enregistrement : ${errorText(e)}`, 8000);
  } finally {
    saving.value = false;
  }
}

// New template: created on the server at once, with default contents
const creating = ref(false);
const newName = ref("");
const creatingBusy = ref(false);

function openNew(): void {
  newName.value = "";
  creating.value = true;
}

async function create(): Promise<void> {
  const name = newName.value.trim();
  const error = newNameError(name, templates.value);
  if (error) {
    toast.show(error);
    return;
  }
  creatingBusy.value = true;
  try {
    const sender = draft.value ?? defaultSender.value;
    await communicationsApi.saveEmailTemplate(newTemplate(name, sender, draft.value?.kind));
    creating.value = false;
    toast.show(`➕ Nouveau modèle « ${name} » créé avec succès !`);
    await loadTemplates(name);
  } catch (e) {
    toast.show(`❌ Erreur : ${errorText(e)}`, 8000);
  } finally {
    creatingBusy.value = false;
  }
}

const deleting = ref(false);

async function remove(): Promise<void> {
  const name = selected.value;
  if (
    !name ||
    !(await dialogs.confirm({
      title: "Supprimer le modèle",
      message: `Êtes-vous sûr de vouloir supprimer définitivement le modèle d'e-mail « ${name} » ?`,
      confirmLabel: "Supprimer",
      variant: "danger",
    }))
  ) {
    return;
  }
  deleting.value = true;
  try {
    await communicationsApi.removeEmailTemplate(name);
    toast.show(`🗑️ Modèle « ${name} » supprimé.`);
    await loadTemplates();
  } catch (e) {
    toast.show(`❌ Erreur lors de la suppression : ${errorText(e)}`, 8000);
  } finally {
    deleting.value = false;
  }
}

// WhatsApp invitation text
const whatsapp = ref("");
const savingWhatsapp = ref(false);

async function loadWhatsapp(): Promise<void> {
  try {
    whatsapp.value = (await communicationsApi.whatsappTemplate()).template;
  } catch (e) {
    console.warn("Texte WhatsApp :", e);
  }
}

async function saveWhatsapp(): Promise<void> {
  const text = whatsapp.value.trim();
  if (!text) {
    toast.show("⚠️ Le texte WhatsApp ne peut pas être vide.");
    return;
  }
  savingWhatsapp.value = true;
  try {
    await communicationsApi.saveWhatsappTemplate(text);
    toast.show("💾 Texte WhatsApp enregistré avec succès !");
  } catch (e) {
    toast.show(`❌ Erreur : ${errorText(e)}`, 8000);
  } finally {
    savingWhatsapp.value = false;
  }
}

onMounted(() => {
  void loadTemplates();
  void loadWhatsapp();
});
</script>

<template>
  <div class="grid items-start gap-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
    <div class="flex min-w-0 flex-col gap-3.5">
      <UiCard>
        <h2 class="mb-2.5 text-[15px] font-bold">📄 Modèle d'e-mail</h2>
        <div class="flex flex-wrap items-end gap-2">
          <div class="min-w-48 flex-1">
            <label for="template-select" class="mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase">
              Sélectionner un modèle
            </label>
            <select
              id="template-select"
              data-testid="template-select"
              :value="selected"
              :disabled="!templates.length"
              class="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px] font-semibold"
              @change="onSelect"
            >
              <optgroup v-for="group in groups" :key="group.kind" :label="group.label">
                <option v-for="t in group.templates" :key="t.name" :value="t.name">
                  {{ optionText(t) }}
                </option>
              </optgroup>
            </select>
          </div>
          <div class="flex gap-1.5">
            <UiButton variant="muted" data-testid="template-new" @click="openNew">➕ Nouveau</UiButton>
            <UiButton
              variant="danger"
              :busy="deleting && 'Suppression…'"
              :disabled="!selected"
              data-testid="template-delete"
              @click="remove"
            >
              🗑️ Supprimer
            </UiButton>
          </div>
        </div>
        <p v-if="loadError" class="mt-2.5 text-[13px] text-red-600">❌ {{ loadError }}</p>
        <p v-else-if="loaded && !templates.length" class="mt-2.5 text-[13px] text-slate-500">
          Aucun modèle pour l'instant : créez-en un avec « Nouveau ».
        </p>
      </UiCard>

      <TemplateForm
        v-if="draft"
        v-model="draft"
        v-model:signature="signature"
        :saving="saving"
        :default-sender="defaultSender"
        :sender-aliases="senderAliases"
        :aliases-error="aliasesError"
        :saved="templates.find((t) => t.name === selected)"
        @save="save"
        @invalid="toast.show"
      />

      <UiCard>
        <form class="flex flex-col gap-2" @submit.prevent="saveWhatsapp">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h2 class="text-[15px] font-bold"><label for="whatsapp">📱 Texte d'invitation WhatsApp</label></h2>
            <UiButton type="submit" variant="muted" small :busy="savingWhatsapp && 'Enregistrement…'" data-testid="whatsapp-save">
              💾 Enregistrer WhatsApp
            </UiButton>
          </div>
          <p class="text-[11.5px] text-slate-500">
            Modèle d'invitation envoyé pour rejoindre le groupe WhatsApp du créneau ou de la compétition :
          </p>
          <textarea
            id="whatsapp"
            v-model="whatsapp"
            rows="3"
            data-testid="whatsapp"
            placeholder="Saisissez le texte WhatsApp…"
            class="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
          />
        </form>
      </UiCard>
    </div>

    <aside v-if="shown" class="flex min-w-0 flex-col gap-2 lg:sticky lg:top-3">
      <h2 class="text-[13px] font-bold text-slate-600">👁 Aperçu en direct de l'e-mail reçu</h2>
      <EmailPreview :preview="shown" :signature="signature" />
    </aside>
  </div>

  <UiDialog v-model:open="creating" title="➕ Nouveau modèle d'e-mail" data-testid="new-template-dialog">
    <form novalidate @submit.prevent="create">
      <label for="new-template-name" class="mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase">Nom du nouveau modèle *</label>
      <input
        id="new-template-name"
        v-model="newName"
        type="text"
        data-testid="new-template-name"
        placeholder="Ex : Rappel stage vacances…"
        class="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-[13px]"
      />
      <UiDialogActions class="mt-4">
        <UiButton variant="muted" @click="creating = false">Annuler</UiButton>
        <UiButton type="submit" :busy="creatingBusy && 'Création…'" data-testid="new-template-create">Créer le modèle</UiButton>
      </UiDialogActions>
    </form>
  </UiDialog>
  <UiToast :message="toast.message.value" />
</template>
