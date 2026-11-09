<script setup lang="ts">
/* Outils › Clés: the panel of one key, its history oldest first (who held it, from when to when; what else happened
   to it) and, for admins, its actions: rename, correct an assignment, delete the latest one (entered by mistake). */
import { inject, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiSidePanel from "../../components/ui/UiSidePanel.vue";
import { dialogs } from "../../composables/dialogs";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { formatDayText } from "../../lib/format";
import { createKeysApi } from "../../services/keys";
import KeyAssignmentEditDialog from "./KeyAssignmentEditDialog.vue";
import { EVENT_LABEL, holderName, STATUS_LABEL, type AssignmentEntry, type HistoryEntry, type Key } from "./keys";

const props = defineProps<{ shownKey: Key; admin: boolean }>();
const emit = defineEmits<{ changed: [message: string]; failed: [message: string]; assign: []; giveBack: []; close: [] }>();

const keysApi = createKeysApi(inject(CLIENT_KEY)!);
const open = ref(true);
watch(open, (value) => !value && emit("close"));
const history = ref<HistoryEntry[] | null>(null);
const editing = ref<AssignmentEntry | null>(null);

async function load(): Promise<void> {
  try {
    history.value = await keysApi.history(props.shownKey.id);
  } catch (e) {
    emit("failed", `Historique illisible : ${errorText(e)}`);
  }
}
// The key shown, or the same key changed (reloaded list)
watch(() => props.shownKey, load, { immediate: true });

const latestAssignment = (entries: readonly HistoryEntry[]) => entries.filter((e) => e.kind === "assignment").at(-1)?.id;

async function rename(): Promise<void> {
  const old = props.shownKey.code;
  const code = await dialogs.prompt({ title: "Modifier le code de la clé", label: "Nouveau code", value: old, confirmLabel: "Renommer" });
  if (!code?.trim() || code.trim() === old) {
    return;
  }
  try {
    await keysApi.rename(props.shownKey.id, code.trim());
    emit("changed", `✅ Clé « ${old} » renommée en « ${code.trim()} ».`);
  } catch (e) {
    emit("failed", errorText(e));
  }
}

async function remove(a: AssignmentEntry): Promise<void> {
  const ok = await dialogs.confirm({
    title: "Supprimer cette attribution ?",
    message: `${holderName(a)}, remise le ${formatDayText(a.given_on)}.\n\nÀ réserver à une saisie erronée : la suppression est notée dans l'historique de la clé.`,
    confirmLabel: "Supprimer",
    variant: "danger",
  });
  if (!ok) {
    return;
  }
  try {
    await keysApi.deleteAssignment(a.id);
    emit("changed", "✅ Attribution supprimée.");
  } catch (e) {
    emit("failed", errorText(e));
  }
}

function edited(message: string): void {
  editing.value = null;
  emit("changed", message);
}
</script>

<template>
  <UiSidePanel id="key-panel" v-model:open="open" :title="`🔑 Clé ${shownKey.code}`" data-testid="key-panel">
    <p class="mb-2 text-xs text-slate-500">{{ STATUS_LABEL[shownKey.status] }}</p>
    <div v-if="admin" class="mb-3 flex flex-wrap gap-2">
      <UiButton v-if="shownKey.status === 'available'" small data-testid="panel-assign" @click="emit('assign')">Remettre</UiButton>
      <UiButton v-if="shownKey.status === 'assigned'" small variant="muted" data-testid="panel-return" @click="emit('giveBack')">
        Retour
      </UiButton>
      <UiButton small variant="muted" data-testid="key-rename" @click="rename">✏️ Modifier le code</UiButton>
    </div>

    <h3 class="mb-1.5 text-[11.5px] font-bold text-slate-500 uppercase">Historique</h3>
    <p v-if="!history" class="text-xs text-slate-500">Chargement…</p>
    <p v-else-if="!history.length" class="text-xs text-slate-500">Jamais remise.</p>
    <ol v-else class="flex flex-col gap-2">
      <li
        v-for="e in history"
        :key="`${e.kind}-${e.id}`"
        data-testid="history-entry"
        class="rounded-lg border border-slate-200 px-2.5 py-2 text-xs"
      >
        <template v-if="e.kind === 'assignment'">
          <b>👤 {{ holderName(e) }}</b>
          <div class="text-slate-600">
            <template v-if="e.returned_on">du {{ formatDayText(e.given_on) }} au {{ formatDayText(e.returned_on) }}</template>
            <template v-else>depuis le {{ formatDayText(e.given_on) }}</template>
          </div>
          <div v-if="e.comment">Remise : {{ e.comment }}</div>
          <div v-if="e.return_comment">Retour : {{ e.return_comment }}</div>
          <div class="text-slate-400">par {{ e.by }}</div>
          <div v-if="admin" class="mt-1 flex gap-2">
            <button
              type="button"
              class="cursor-pointer text-accent hover:underline"
              :data-testid="`assignment-edit-${e.id}`"
              @click="editing = e"
            >
              Corriger
            </button>
            <button
              v-if="e.id === latestAssignment(history)"
              type="button"
              class="cursor-pointer text-red-600 hover:underline"
              :data-testid="`assignment-delete-${e.id}`"
              @click="remove(e)"
            >
              Supprimer
            </button>
          </div>
        </template>
        <template v-else>
          <b>{{ EVENT_LABEL[e.type] }}</b>
          le {{ formatDayText(e.date) }}
          <div v-if="e.comment">{{ e.comment }}</div>
          <div class="text-slate-400">par {{ e.by }}</div>
        </template>
      </li>
    </ol>

    <KeyAssignmentEditDialog :assignment="editing" @close="editing = null" @done="edited" @failed="(m) => emit('failed', m)" />
  </UiSidePanel>
</template>
