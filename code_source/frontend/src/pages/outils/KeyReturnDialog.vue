<script setup lang="ts">
/* Outils › Clés: records the return of a key (admin); the key becomes available again. */
import { computed, inject, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { formatDayText } from "../../lib/format";
import { createKeysApi } from "../../services/keys";
import { todayIso } from "../competitions/competitions";
import { holderName, type Key } from "./keys";

const props = defineProps<{ keyToReturn: Key | null }>();
const emit = defineEmits<{ done: [message: string]; failed: [message: string]; close: [] }>();

const keysApi = createKeysApi(inject(CLIENT_KEY)!);
const open = computed({
  get: () => props.keyToReturn !== null,
  set: (value) => !value && emit("close"),
});
const returnedOn = ref(todayIso());
const comment = ref("");
const busy = ref(false);

watch(
  () => props.keyToReturn,
  () => {
    returnedOn.value = todayIso();
    comment.value = "";
  },
);

async function submit(): Promise<void> {
  const key = props.keyToReturn;
  if (!key) {
    return;
  }
  busy.value = true;
  try {
    await keysApi.giveBack(key.id, { returned_on: returnedOn.value, comment: comment.value });
    emit("done", `✅ Retour de la clé « ${key.code} » enregistré.`);
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
    :title="`↩️ Retour de la clé « ${keyToReturn?.code} »`"
    :description="
      keyToReturn?.holder
        ? `Détenue par ${holderName(keyToReturn.holder)} depuis le ${formatDayText(keyToReturn.holder.given_on)}.`
        : undefined
    "
    data-testid="key-return-dialog"
  >
    <form novalidate @submit.prevent="submit">
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label for="return-date" :class="label">Rendue le *</label>
          <input id="return-date" v-model="returnedOn" type="date" required data-testid="return-date" :class="field" />
        </div>
        <div>
          <label for="return-comment" :class="label">Commentaire</label>
          <input id="return-comment" v-model="comment" type="text" maxlength="500" data-testid="return-comment" :class="field" />
        </div>
      </div>
      <UiDialogActions class="mt-4">
        <UiButton variant="muted" @click="open = false">Annuler</UiButton>
        <UiButton type="submit" :disabled="!returnedOn" :busy="busy && 'Enregistrement…'" data-testid="return-submit">
          Enregistrer le retour
        </UiButton>
      </UiDialogActions>
    </form>
  </UiDialog>
</template>
