<script setup lang="ts">
/* Edits an e-mail template: name, sender, subject and body, with the variables and the bold / italic / underline / link
   tags inserted at the cursor. Submitting checks the template first: "save" when it can be saved, else "invalid"
   with the reason. */
import { nextTick, ref, useTemplateRef } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import {
  insertText,
  linkTags,
  linkTarget,
  SENDER_SUGGESTIONS,
  templateError,
  VARIABLES,
  wrapSelection,
  type Edit,
  type Template,
} from "./editor";

defineProps<{ saving?: boolean }>();
const emit = defineEmits<{ save: []; invalid: [message: string] }>();
const draft = defineModel<Template>({ required: true });
const signature = defineModel<boolean>("signature", { default: true });

const showVariables = ref(false);
const body = useTemplateRef<HTMLTextAreaElement>("body");

async function edit(change: (value: string, start: number, end: number) => Edit): Promise<void> {
  const area = body.value!;
  const result = change(draft.value.body, area.selectionStart, area.selectionEnd);
  draft.value.body = result.value;
  await nextTick();
  area.focus();
  area.setSelectionRange(result.start, result.end);
}

const insertVariable = (name: string) => edit((v, s, e) => insertText(v, s, e, name));
const wrap = (tag: string) => edit((v, s, e) => wrapSelection(v, s, e, `<${tag}>`, `</${tag}>`));

function addLink(): void {
  const url = linkTarget(prompt("Entrez l'URL du lien (ex: https://www.alj-escalade.fr) :", "https://"));
  if (url) void edit((v, s, e) => wrapSelection(v, s, e, ...linkTags(url)));
}

function submit(): void {
  const error = templateError(draft.value);
  if (error) emit("invalid", error);
  else emit("save");
}

const FORMATS = [
  { tag: "b", label: "B", title: "Gras", testid: "format-bold", class: "" },
  { tag: "i", label: "I", title: "Italique", testid: "format-italic", class: "italic" },
  { tag: "u", label: "U", title: "Souligné", testid: "format-underline", class: "underline" },
];
const INPUT = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]";
const LABEL = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const TOOL =
  "cursor-pointer rounded border border-slate-300 bg-white px-2 py-0.5 text-xs font-semibold text-slate-700 hover:border-slate-400 hover:bg-slate-50";
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
            placeholder="inscription@alj-escalade.fr"
            :class="INPUT"
          />
          <datalist id="sender-suggestions">
            <option v-for="address in SENDER_SUGGESTIONS" :key="address" :value="address" />
          </datalist>
        </div>
        <div>
          <label for="sender-name" :class="LABEL">Nom d'affichage</label>
          <input
            id="sender-name"
            v-model="draft.sender_name"
            type="text"
            data-testid="sender-name"
            placeholder="Amicale Laïque Jonage - Inscriptions"
            :class="INPUT"
          />
        </div>
      </div>

      <div>
        <label for="subject" :class="LABEL">Objet de l'e-mail *</label>
        <input
          id="subject"
          v-model="draft.subject"
          type="text"
          data-testid="subject"
          placeholder="Sujet de votre message…"
          :class="INPUT"
        />
      </div>

      <div>
        <div class="mb-1 flex flex-wrap items-center justify-between gap-2">
          <label for="body" :class="[LABEL, 'mb-0']">Corps du message *</label>
          <button
            type="button"
            :class="TOOL"
            :aria-expanded="showVariables"
            aria-controls="variables"
            data-testid="variables-toggle"
            @click="showVariables = !showVariables"
          >
            { } Variables disponibles
          </button>
        </div>
        <div
          v-show="showVariables"
          id="variables"
          data-testid="variables"
          class="mb-2 rounded-md border border-slate-300 bg-slate-50 px-2.5 py-2"
        >
          <p class="mb-1.5 text-[11px] text-slate-500">Cliquez sur une variable pour l'insérer dans le texte :</p>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="name in VARIABLES"
              :key="name"
              type="button"
              class="cursor-pointer rounded border border-slate-300 bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] hover:border-accent hover:text-accent"
              @click="insertVariable(name)"
            >
              {{ name }}
            </button>
          </div>
        </div>
        <div class="mb-1.5 flex gap-1.5" role="toolbar" aria-label="Mise en forme">
          <button
            v-for="f in FORMATS"
            :key="f.tag"
            type="button"
            :title="f.title"
            :aria-label="f.title"
            :data-testid="f.testid"
            :class="[TOOL, f.class]"
            @click="wrap(f.tag)"
          >
            {{ f.label }}
          </button>
          <button type="button" title="Insérer un lien web" data-testid="format-link" :class="TOOL" @click="addLink">🔗 Lien</button>
        </div>
        <textarea
          id="body"
          ref="body"
          v-model="draft.body"
          rows="11"
          data-testid="body"
          placeholder="Saisissez le corps du message…"
          :class="[INPUT, 'leading-normal']"
        />
      </div>

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
