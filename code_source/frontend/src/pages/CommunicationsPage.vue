<script setup lang="ts">
/* Communications (admins): the e-mail templates used by the Adhérents and Compétitions pages (create, edit, rename,
   delete) with a live preview, and the WhatsApp invitation text. Online only: nothing is kept on the device. */
import { computed, inject, onMounted, ref } from "vue";
import AppShell from "../components/AppShell.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiDialogActions from "../components/ui/UiDialogActions.vue";
import UiCard from "../components/ui/UiCard.vue";
import UiDialog from "../components/ui/UiDialog.vue";
import UiToast from "../components/ui/UiToast.vue";
import { useToast } from "../composables/toast";
import { CLIENT_KEY, errorText } from "../lib/client";
import { createCommunicationsApi } from "../services/communications";
import EmailPreview from "./communications/EmailPreview.vue";
import {
  DEFAULT_SENDER_EMAIL,
  DEFAULT_SENDER_NAME,
  initialTemplate,
  newNameError,
  newTemplate,
  preview,
  type Template,
} from "./communications/editor";
import TemplateForm from "./communications/TemplateForm.vue";

const communicationsApi = createCommunicationsApi(inject(CLIENT_KEY)!);
const toast = useToast();

// E-mail templates
const templates = ref<Template[]>([]);
const loaded = ref(false);
const loadError = ref("");
/** Saved name of the template being edited (the server renames it when the title changes). */
const selected = ref("");
const draft = ref<Template | null>(null);
const signature = ref(true);
const saving = ref(false);
const shown = computed(() => (draft.value ? preview(draft.value) : null));

function select(template: Template | undefined): void {
  selected.value = template?.name ?? "";
  draft.value = template ? { ...template } : null;
}

async function loadTemplates(wanted?: string): Promise<void> {
  try {
    templates.value = (await communicationsApi.emailTemplates()).templates;
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
  const template = draft.value!;
  saving.value = true;
  try {
    const saved = await communicationsApi.saveEmailTemplate({ ...template, old_name: selected.value });
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
    const sender = draft.value ?? { sender_email: DEFAULT_SENDER_EMAIL, sender_name: DEFAULT_SENDER_NAME };
    await communicationsApi.saveEmailTemplate(newTemplate(name, sender));
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
  if (!name || !confirm(`Êtes-vous sûr de vouloir supprimer définitivement le modèle d'e-mail « ${name} » ?`)) {
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
  <AppShell page="communications" title="Communications & Modèles d'e-mails">
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
                <option v-for="t in templates" :key="t.name" :value="t.name">{{ t.name }}</option>
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

        <TemplateForm v-if="draft" v-model="draft" v-model:signature="signature" :saving="saving" @save="save" @invalid="toast.show" />

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
        <label for="new-template-name" class="mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase">
          Nom du nouveau modèle *
        </label>
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
  </AppShell>
</template>
