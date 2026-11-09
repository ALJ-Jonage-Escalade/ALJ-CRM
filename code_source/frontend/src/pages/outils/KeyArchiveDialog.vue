<script setup lang="ts">
/* Outils › Clés: archives a lost or broken key, with its reason (admin). Never deleted: the key keeps its history and
   can be restored. A held key's assignment ends on the archive date. */
import { computed, inject, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createKeysApi } from "../../services/keys";
import { todayIso } from "../competitions/competitions";
import { holderName, type Key } from "./keys";

const props = defineProps<{ keyToArchive: Key | null }>();
const emit = defineEmits<{ done: [message: string]; failed: [message: string]; close: [] }>();

const keysApi = createKeysApi(inject(CLIENT_KEY)!);
const open = computed({
  get: () => props.keyToArchive !== null,
  set: (value) => !value && emit("close"),
});
const archivedOn = ref(todayIso());
const comment = ref("");
const busy = ref(false);

watch(
  () => props.keyToArchive,
  () => {
    archivedOn.value = todayIso();
    comment.value = "";
  },
);

async function submit(): Promise<void> {
  const key = props.keyToArchive;
  if (!key || !comment.value.trim()) {
    return;
  }
  busy.value = true;
  try {
    await keysApi.archive(key.id, { archived_on: archivedOn.value, comment: comment.value });
    emit("done", `✅ Clé « ${key.code} » archivée.`);
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
  <UiDialog v-model:open="open" :title="`📦 Archiver la clé « ${keyToArchive?.code} »`" data-testid="archive-dialog">
    <p class="mb-3 text-[13px] text-slate-600">
      Une clé archivée ne peut plus être remise ; elle garde son historique et peut être restaurée.
      <template v-if="keyToArchive?.holder">
        {{ holderName(keyToArchive.holder) }} ne la détiendra plus à partir de la date d'archivage.
      </template>
    </p>
    <form novalidate @submit.prevent="submit">
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label for="archive-date" :class="label">Archivée le *</label>
          <input id="archive-date" v-model="archivedOn" type="date" required data-testid="archive-date" :class="field" />
        </div>
        <div>
          <label for="archive-comment" :class="label">Raison *</label>
          <input
            id="archive-comment"
            v-model="comment"
            type="text"
            required
            maxlength="500"
            placeholder="Ex : Perdue, cassée…"
            data-testid="archive-comment"
            :class="field"
          />
        </div>
      </div>
      <UiDialogActions class="mt-4">
        <UiButton variant="muted" @click="open = false">Annuler</UiButton>
        <UiButton
          type="submit"
          variant="warning"
          :disabled="!archivedOn || !comment.trim()"
          :busy="busy && 'Archivage…'"
          data-testid="archive-submit"
        >
          Archiver
        </UiButton>
      </UiDialogActions>
    </form>
  </UiDialog>
</template>
