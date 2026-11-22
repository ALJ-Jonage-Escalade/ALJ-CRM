<script setup lang="ts">
/* A subject or body of an e-mail template, written with the variables' French labels ({Prénom}): a picker inserts
   them at the cursor, a multi-line field adds the bold / italic / underline / link buttons, and an unknown variable
   is shown under the field. The text stays in labels: the page converts it to keys (toKeys) to save or send it. */
import { computed, nextTick, ref, useTemplateRef } from "vue";
import { templateError, variablesOf, type TemplateKind } from "../lib/templateVariables";
import { insertText, linkTags, linkTarget, wrapSelection, type Edit } from "../lib/textEdit";
import { dialogs } from "../composables/dialogs";

/** id: of the field, also the prefix of its data-testid's; kind: the variables offered (all of them without). */
const props = withDefaults(
  defineProps<{ id: string; label: string; kind?: TemplateKind; multiline?: boolean; rows?: number; placeholder?: string }>(),
  { kind: undefined, multiline: false, rows: 11, placeholder: "" },
);
const text = defineModel<string>({ required: true });

const showVariables = ref(false);
const field = useTemplateRef<HTMLInputElement | HTMLTextAreaElement>("field");
const offered = computed(() => variablesOf(props.kind));
const error = computed(() => templateError([text.value], props.kind));

async function edit(change: (value: string, start: number, end: number) => Edit): Promise<void> {
  const element = field.value;
  if (!element) {
    return;
  }
  const end = element.selectionEnd ?? text.value.length;
  const result = change(text.value, element.selectionStart ?? end, end);
  text.value = result.value;
  await nextTick();
  element.focus();
  element.setSelectionRange(result.start, result.end);
}

const token = (label: string): string => `{${label}}`;
const insertVariable = (label: string) => edit((v, s, e) => insertText(v, s, e, token(label)));
const wrap = (tag: string) => edit((v, s, e) => wrapSelection(v, s, e, `<${tag}>`, `</${tag}>`));

async function addLink(): Promise<void> {
  const url = linkTarget(
    await dialogs.prompt({
      title: "Insérer un lien",
      label: "URL du lien (ex : https://www.alj-escalade.fr)",
      value: "https://",
      confirmLabel: "Insérer",
    }),
  );
  if (url) {
    void edit((v, s, e) => wrapSelection(v, s, e, ...linkTags(url)));
  }
}

const FORMATS = [
  { tag: "b", label: "B", title: "Gras", testid: "format-bold", class: "" },
  { tag: "i", label: "I", title: "Italique", testid: "format-italic", class: "italic" },
  { tag: "u", label: "U", title: "Souligné", testid: "format-underline", class: "underline" },
];
const INPUT = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]";
const LABEL = "mb-0 block text-[11.5px] font-semibold text-slate-500 uppercase";
const TOOL =
  "cursor-pointer rounded border border-slate-300 bg-white px-2 py-0.5 text-xs font-semibold text-slate-700 hover:border-slate-400 hover:bg-slate-50";
</script>

<template>
  <div>
    <div class="mb-1 flex flex-wrap items-center justify-between gap-2">
      <label :for="id" :class="LABEL">{{ label }}</label>
      <button
        type="button"
        :class="TOOL"
        :aria-expanded="showVariables"
        :aria-controls="`${id}-variables`"
        :data-testid="`${id}-variables-toggle`"
        @click="showVariables = !showVariables"
      >
        { } Variables
      </button>
    </div>
    <div
      v-show="showVariables"
      :id="`${id}-variables`"
      :data-testid="`${id}-variables`"
      class="mb-2 rounded-md border border-slate-300 bg-slate-50 px-2.5 py-2"
    >
      <p class="mb-1.5 text-[11px] text-slate-500">Cliquez sur une variable pour l'insérer dans le texte :</p>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="variable in offered"
          :key="variable.key"
          type="button"
          class="cursor-pointer rounded border border-slate-300 bg-slate-100 px-1.5 py-0.5 text-[11px] hover:border-accent hover:text-accent"
          @click="insertVariable(variable.label)"
        >
          {{ token(variable.label) }}
        </button>
      </div>
    </div>
    <div v-if="multiline" class="mb-1.5 flex gap-1.5" role="toolbar" aria-label="Mise en forme">
      <button
        v-for="f in FORMATS"
        :key="f.tag"
        type="button"
        :title="f.title"
        :aria-label="f.title"
        :data-testid="`${id}-${f.testid}`"
        :class="[TOOL, f.class]"
        @click="wrap(f.tag)"
      >
        {{ f.label }}
      </button>
      <button type="button" title="Insérer un lien web" :data-testid="`${id}-format-link`" :class="TOOL" @click="addLink">🔗 Lien</button>
    </div>
    <textarea
      v-if="multiline"
      :id="id"
      ref="field"
      v-model="text"
      :rows="rows"
      :data-testid="id"
      :placeholder="placeholder"
      :aria-invalid="error !== null"
      :class="[INPUT, 'leading-normal']"
    />
    <input
      v-else
      :id="id"
      ref="field"
      v-model="text"
      type="text"
      :data-testid="id"
      :placeholder="placeholder"
      :aria-invalid="error !== null"
      :class="INPUT"
    />
    <p v-if="error" :data-testid="`${id}-error`" role="alert" class="mt-1 text-xs font-semibold text-red-600">⚠️ {{ error }}</p>
  </div>
</template>
