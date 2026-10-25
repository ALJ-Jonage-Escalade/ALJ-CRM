<script setup lang="ts">
/* Shows the confirmation or text-entry request of composables/dialogs.ts. The focus starts on « Annuler » (a
   confirmation) or in the field (a text entry). */
import { computed, ref, watch } from "vue";
import { cancelDialog, pendingDialog } from "../../composables/dialogs";
import UiButton from "./UiButton.vue";
import UiDialog from "./UiDialog.vue";
import UiDialogActions from "./UiDialogActions.vue";

const open = computed({
  get: () => pendingDialog.value !== null,
  set: (now) => {
    if (!now) {
      cancelDialog();
    }
  },
});
// Kept while the dialog closes, so its text does not vanish before it does
const shown = ref(pendingDialog.value);
const text = ref("");
watch(pendingDialog, (now) => {
  if (now) {
    shown.value = now;
    text.value = now.kind === "prompt" ? (now.request.value ?? "") : "";
  }
});

function accept(): void {
  const now = pendingDialog.value;
  if (now?.kind === "confirm") {
    now.answer(true);
  } else if (now?.kind === "prompt") {
    now.answer(text.value);
  }
}
</script>

<template>
  <UiDialog v-if="shown" v-model:open="open" :title="shown.request.title" data-testid="dialog-host">
    <form @submit.prevent="accept">
      <p v-if="shown.request.message" data-testid="dialog-message" class="mb-4 text-[13px] whitespace-pre-line text-slate-700">
        {{ shown.request.message }}
      </p>
      <label v-if="shown.kind === 'prompt'" class="mb-4 block text-[13px] font-semibold text-slate-700">
        {{ shown.request.label }}
        <input
          v-model="text"
          data-testid="dialog-input"
          class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal focus:border-accent focus:outline-none"
        />
      </label>
      <UiDialogActions>
        <UiButton variant="muted" data-testid="dialog-cancel" @click="open = false">Annuler</UiButton>
        <UiButton type="submit" :variant="shown.request.variant ?? 'primary'" data-testid="dialog-confirm">
          {{ shown.request.confirmLabel ?? "Confirmer" }}
        </UiButton>
      </UiDialogActions>
    </form>
  </UiDialog>
</template>
