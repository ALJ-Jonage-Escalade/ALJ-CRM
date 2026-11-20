<script setup lang="ts">
/* Correction of a HelloAsso registration's data, opened from a row of the import preview: each correctable field with
   the value HelloAsso gave (struck through once corrected), an editable value checked by the server as it is typed
   (same rules as the import, nothing saved), and its problems. Saving or undoing a correction answers the preview
   recomputed with it, given to the page. Online only, like the whole import. */
import { computed, inject, ref, watch } from "vue";
import UiBadge from "../../../components/ui/UiBadge.vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiDialog from "../../../components/ui/UiDialog.vue";
import { CLIENT_KEY, errorText } from "../../../lib/client";
import { choicesWith, COUNTRY_CHOICES, NATIONALITY_CHOICES } from "../../../lib/countries";
import { createMembersApi, type MembershipField } from "../../../services/members";
import { CORRECTABLE_FIELDS, personLabel, type MembershipPreview, type MembershipRow } from "./helloassoImport";

type Issue = MembershipRow["issues"][number];

const props = defineProps<{ row: MembershipRow; campaign: string | null }>();
const emit = defineEmits<{ updated: [preview: MembershipPreview] }>();
const open = defineModel<boolean>("open", { required: true });

const membersApi = createMembersApi(inject(CLIENT_KEY)!);

// What the admin types, by field; the issues the server finds in it (undefined: the row's own, for its current value)
const drafts = ref<Partial<Record<MembershipField, string>>>({});
const checked = ref<Partial<Record<MembershipField, Issue[]>>>({});
const busy = ref<MembershipField | null>(null);
const failure = ref("");

const CHECK_DELAY_MS = 400;
const timers = new Map<MembershipField, ReturnType<typeof setTimeout>>();

function current(field: MembershipField): string {
  return props.row.values[field] ?? "";
}

function correctionOf(field: MembershipField): MembershipRow["corrections"][number] | undefined {
  return props.row.corrections.find((correction) => correction.field === field);
}

function reset(): void {
  drafts.value = Object.fromEntries(CORRECTABLE_FIELDS.map(({ field }) => [field, current(field)]));
  checked.value = {};
  failure.value = "";
}

watch(open, (isOpen) => {
  if (isOpen) {
    reset();
  }
});
// The row recomputed after a save: the fields show its values again
watch(() => props.row, reset);

const fields = computed(() =>
  CORRECTABLE_FIELDS.map(({ field, label }) => ({
    field,
    label,
    correction: correctionOf(field),
    helloasso: correctionOf(field)?.helloasso_value ?? current(field),
    issues: checked.value[field] ?? props.row.issues.filter((issue) => issue.field === field),
    changed: (drafts.value[field] ?? "") !== current(field),
    options:
      field === "country"
        ? choicesWith(COUNTRY_CHOICES, current(field))
        : field === "nationality"
          ? choicesWith(NATIONALITY_CHOICES, current(field))
          : null,
  })),
);

/** The server checks the typed value a moment after the last key. */
function type(field: MembershipField, value: string): void {
  drafts.value = { ...drafts.value, [field]: value };
  clearTimeout(timers.get(field));
  if (value === current(field)) {
    checked.value = { ...checked.value, [field]: undefined };
    return;
  }
  timers.set(
    field,
    setTimeout(() => void check(field, value), CHECK_DELAY_MS),
  );
}

async function check(field: MembershipField, value: string): Promise<void> {
  try {
    const result = await membersApi.helloAssoCheckValue(field, value);
    if (drafts.value[field] === value) {
      checked.value = { ...checked.value, [field]: result.issues };
    }
  } catch (e) {
    console.warn("Contrôle de la valeur :", e);
  }
}

async function run(field: MembershipField, action: () => Promise<MembershipPreview>): Promise<void> {
  busy.value = field;
  failure.value = "";
  try {
    emit("updated", await action());
  } catch (e) {
    failure.value = errorText(e);
  } finally {
    busy.value = null;
  }
}

function save(field: MembershipField): Promise<void> {
  return run(field, () => membersApi.helloAssoSaveCorrection(props.row.item_id, field, drafts.value[field] ?? "", props.campaign));
}

function undo(field: MembershipField): Promise<void> {
  return run(field, () => membersApi.helloAssoRemoveCorrection(props.row.item_id, field, props.campaign));
}
</script>

<template>
  <UiDialog
    v-model:open="open"
    wide
    data-testid="ha-fix-dialog"
    :title="`✏️ Corriger l'inscription de ${personLabel(row)}`"
    description="La correction remplace la valeur HelloAsso jusqu'à l'import, et sera écrite sur la fiche de l'adhérent (même lors d'un renouvellement)."
  >
    <p v-if="failure" data-testid="ha-fix-error" class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
      ❌ {{ failure }}
    </p>
    <div class="flex flex-col gap-3">
      <div
        v-for="item in fields"
        :key="item.field"
        :data-testid="`ha-fix-${item.field}`"
        :class="['rounded-lg border p-2.5', item.issues.length ? 'border-amber-300 bg-amber-50/40' : 'border-slate-200']"
      >
        <div class="mb-1 flex flex-wrap items-center gap-2 text-[13px] font-semibold">
          <label :for="`ha-fix-input-${item.field}`">{{ item.label }}</label>
          <UiBadge v-if="item.correction" color="blue" variant="soft">corrigée</UiBadge>
        </div>
        <p class="mb-1 text-xs text-slate-500">
          HelloAsso :
          <s v-if="item.correction" data-testid="ha-fix-helloasso">{{ item.helloasso || "—" }}</s>
          <span v-else data-testid="ha-fix-helloasso">{{ item.helloasso || "—" }}</span>
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <select
            v-if="item.options"
            :id="`ha-fix-input-${item.field}`"
            :value="drafts[item.field] ?? ''"
            class="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-[13px]"
            @change="type(item.field, ($event.target as HTMLSelectElement).value)"
          >
            <option value="">—</option>
            <option v-for="option in item.options" :key="option.value" :value="option.value">{{ option.text }}</option>
          </select>
          <input
            v-else
            :id="`ha-fix-input-${item.field}`"
            data-testid="ha-fix-input"
            :value="drafts[item.field] ?? ''"
            class="min-w-0 flex-1 rounded-md border border-slate-300 px-2 py-1 text-[13px]"
            @input="type(item.field, ($event.target as HTMLInputElement).value)"
          />
          <UiButton
            small
            data-testid="ha-fix-save"
            :disabled="!item.changed || !!busy"
            :busy="busy === item.field && 'Enregistrement…'"
            @click="save(item.field)"
          >
            Enregistrer
          </UiButton>
          <UiButton v-if="item.correction" small variant="muted" data-testid="ha-fix-undo" :disabled="!!busy" @click="undo(item.field)">
            Annuler la correction
          </UiButton>
        </div>
        <ul v-if="item.issues.length" class="mt-1 space-y-0.5 text-xs">
          <li
            v-for="issue in item.issues"
            :key="issue.code"
            data-testid="ha-fix-issue"
            :class="issue.blocking ? 'font-semibold text-red-700' : 'text-amber-700'"
          >
            {{ issue.blocking ? "⛔" : "⚠️" }} {{ issue.message }}
          </li>
        </ul>
      </div>
    </div>
  </UiDialog>
</template>
