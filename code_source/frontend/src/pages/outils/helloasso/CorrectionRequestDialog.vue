<script setup lang="ts">
/* Correction request to the families, from the HelloAsso import preview: the rows with problems to choose from (those
   picked on opening checked), what the send will be (one e-mail per order, to the payer) and the e-mail of the first
   order as the server would send it. Nothing leaves before « Envoyer ». Online only, like the whole import. */
import { computed, inject, ref, watch } from "vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiDialog from "../../../components/ui/UiDialog.vue";
import UiDialogActions from "../../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText, type Schemas } from "../../../lib/client";
import { createMembersApi } from "../../../services/members";
import { lastRequestText, personLabel, requestSummary, type MembershipRow } from "./helloassoImport";

// rows: the rows that can be asked; picked: the item ids checked on opening
const props = defineProps<{ rows: MembershipRow[]; picked: number[]; campaign: string | null }>();
const emit = defineEmits<{ sent: [] }>();
const open = defineModel<boolean>("open", { required: true });

const membersApi = createMembersApi(inject(CLIENT_KEY)!);

const checked = ref<number[]>([]);
const example = ref<Schemas["CorrectionEmail"] | null>(null);
const busy = ref<"example" | "send" | null>(null);
const failure = ref("");
const done = ref("");

const chosen = computed(() => props.rows.filter((row) => checked.value.includes(row.item_id)));
const summary = computed(() => requestSummary(chosen.value));
// The chosen registrations the family was already asked about: shown before sending again
const alreadyAsked = computed(() => chosen.value.filter((row) => row.last_request));

watch(
  open,
  (isOpen) => {
    if (isOpen) {
      checked.value = [...props.picked];
      done.value = "";
      failure.value = "";
    }
  },
  { immediate: true },
);

// The example follows the choice: the e-mail of the first order of the checked rows
watch(
  checked,
  async (itemIds) => {
    example.value = null;
    if (!itemIds.length) {
      return;
    }
    busy.value = "example";
    failure.value = "";
    try {
      const shown = await membersApi.helloAssoRequestPreview(itemIds, props.campaign);
      if (checked.value === itemIds) {
        example.value = shown.example;
      }
    } catch (e) {
      failure.value = errorText(e);
    } finally {
      busy.value = null;
    }
  },
  { immediate: true },
);

function toggle(itemId: number, isChecked: boolean): void {
  checked.value = isChecked ? [...checked.value, itemId] : checked.value.filter((id) => id !== itemId);
}

async function send(): Promise<void> {
  busy.value = "send";
  failure.value = "";
  try {
    const result = await membersApi.helloAssoRequestCorrections(checked.value, props.campaign);
    done.value =
      `✅ ${result.sent} e-mail(s) envoyé(s)` +
      (result.failed ? `, ${result.failed} en échec` : "") +
      (result.log_notice ? ` — ${result.log_notice}` : "");
    emit("sent");
  } catch (e) {
    failure.value = errorText(e);
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <UiDialog
    v-model:open="open"
    wide
    data-testid="ha-request-dialog"
    title="📧 Demander une correction aux familles"
    description="Un e-mail par commande HelloAsso, au payeur (l'e-mail du club de l'adhérent en copie), listant les informations à corriger. La famille répond par e-mail ; vous saisissez ensuite la correction."
  >
    <p
      v-if="failure"
      data-testid="ha-request-error"
      class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700"
    >
      ❌ {{ failure }}
    </p>
    <p
      v-if="done"
      data-testid="ha-request-done"
      class="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[13px] text-emerald-800"
    >
      {{ done }}
    </p>
    <fieldset class="mb-3 max-h-48 overflow-y-auto rounded-lg border border-slate-200 p-2 text-[13px]">
      <legend class="px-1 font-semibold">Inscriptions</legend>
      <label v-for="row in rows" :key="row.item_id" class="flex items-center gap-2 py-0.5">
        <input
          type="checkbox"
          data-testid="ha-request-row"
          :checked="checked.includes(row.item_id)"
          :disabled="!!done"
          @change="toggle(row.item_id, ($event.target as HTMLInputElement).checked)"
        />
        {{ personLabel(row) }}
        <span class="text-slate-500">— {{ row.issues.length }} problème(s), commande {{ row.order_ref }}</span>
      </label>
    </fieldset>
    <p data-testid="ha-request-summary" class="mb-2 text-[13px] font-semibold">{{ summary.text }}</p>
    <div
      v-if="alreadyAsked.length && !done"
      data-testid="ha-request-again"
      role="alert"
      class="mb-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[13px] text-amber-900"
    >
      <p class="font-semibold">⚠️ Déjà demandé à la famille — renvoyer seulement si nécessaire :</p>
      <ul class="mt-1 list-disc pl-5">
        <li v-for="row in alreadyAsked" :key="row.item_id">{{ personLabel(row) }} : {{ lastRequestText(row) }}</li>
      </ul>
    </div>
    <div v-if="example" data-testid="ha-request-example" class="mb-3 rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs">
      <p class="mb-1 text-slate-500">Exemple (première commande) :</p>
      <p>
        <b>À :</b>
        {{ example.to }}
      </p>
      <p v-if="example.cc.length">
        <b>Copie :</b>
        {{ example.cc.join(", ") }}
      </p>
      <p class="mb-1">
        <b>Objet :</b>
        {{ example.subject }}
      </p>
      <pre class="font-sans whitespace-pre-wrap">{{ example.body }}</pre>
    </div>
    <UiDialogActions>
      <UiButton variant="muted" @click="open = false">{{ done ? "Fermer" : "Annuler" }}</UiButton>
      <UiButton
        v-if="!done"
        data-testid="ha-request-send"
        :disabled="!summary.emails || !!busy"
        :busy="busy === 'send' && 'Envoi…'"
        @click="send"
      >
        Envoyer {{ summary.emails > 1 ? `les ${summary.emails} e-mails` : "l'e-mail" }}
      </UiButton>
    </UiDialogActions>
  </UiDialog>
</template>
