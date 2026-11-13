<script setup lang="ts">
/* Outils › Clés: corrects the dates and comments of an assignment (admin). The return date only exists, and can only be
   changed, on a key given back: the return itself is recorded from the key. */
import { computed, inject, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createKeysApi } from "../../services/keys";
import { holderName, type AssignmentEntry } from "./keys";

const props = defineProps<{ assignment: AssignmentEntry | null }>();
const emit = defineEmits<{ done: [message: string]; failed: [message: string]; close: [] }>();

const keysApi = createKeysApi(inject(CLIENT_KEY)!);
const open = computed({
  get: () => props.assignment !== null,
  set: (value) => !value && emit("close"),
});
const givenOn = ref("");
const returnedOn = ref("");
const comment = ref("");
const returnComment = ref("");
const busy = ref(false);

watch(
  () => props.assignment,
  (a) => {
    givenOn.value = a?.given_on ?? "";
    returnedOn.value = a?.returned_on ?? "";
    comment.value = a?.comment ?? "";
    returnComment.value = a?.return_comment ?? "";
  },
);

async function submit(): Promise<void> {
  const a = props.assignment;
  if (!a) {
    return;
  }
  busy.value = true;
  try {
    await keysApi.correctAssignment(a.id, {
      given_on: givenOn.value,
      returned_on: a.returned_on === null ? null : returnedOn.value,
      comment: comment.value,
      return_comment: returnComment.value,
    });
    emit("done", "✅ Attribution corrigée.");
  } catch (e) {
    emit("failed", errorText(e));
  } finally {
    busy.value = false;
  }
}

const label = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const field = "w-full rounded-lg border border-slate-300 px-2.5 py-2 text-[13px]";
</script>

<template>
  <UiDialog
    v-model:open="open"
    title="✏️ Corriger l'attribution"
    :description="assignment ? holderName(assignment) : undefined"
    data-testid="assignment-edit-dialog"
  >
    <form novalidate @submit.prevent="submit">
      <div class="grid gap-3">
        <div>
          <label for="edit-given-on" :class="label">Remise le *</label>
          <input id="edit-given-on" v-model="givenOn" type="date" required data-testid="edit-given-on" :class="field" />
        </div>
        <div>
          <label for="edit-comment" :class="label">Commentaire de remise</label>
          <textarea id="edit-comment" v-model="comment" rows="3" maxlength="500" data-testid="edit-comment" :class="field" />
        </div>
        <template v-if="assignment?.returned_on">
          <div>
            <label for="edit-returned-on" :class="label">Rendue le *</label>
            <input id="edit-returned-on" v-model="returnedOn" type="date" required data-testid="edit-returned-on" :class="field" />
          </div>
          <div>
            <label for="edit-return-comment" :class="label">Commentaire de retour</label>
            <textarea
              id="edit-return-comment"
              v-model="returnComment"
              rows="3"
              maxlength="500"
              data-testid="edit-return-comment"
              :class="field"
            />
          </div>
        </template>
      </div>
      <UiDialogActions class="mt-4">
        <UiButton variant="muted" @click="open = false">Annuler</UiButton>
        <UiButton
          type="submit"
          :disabled="!givenOn || (!!assignment?.returned_on && !returnedOn)"
          :busy="busy && 'Enregistrement…'"
          data-testid="edit-submit"
        >
          Enregistrer
        </UiButton>
      </UiDialogActions>
    </form>
  </UiDialog>
</template>
