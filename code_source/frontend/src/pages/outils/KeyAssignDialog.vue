<script setup lang="ts">
/* Outils › Clés: hands an available key to a member of the active season who holds none (admin). */
import { computed, inject, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createKeysApi } from "../../services/keys";
import { createMembersApi } from "../../services/members";
import { todayIso } from "../competitions/competitions";
import { candidates, type Candidate, type Key } from "./keys";

const props = defineProps<{ keyToAssign: Key | null; keys: readonly Key[] }>();
const emit = defineEmits<{ done: [message: string]; failed: [message: string]; close: [] }>();

const client = inject(CLIENT_KEY)!;
const keysApi = createKeysApi(client);
const membersApi = createMembersApi(client);

const open = computed({
  get: () => props.keyToAssign !== null,
  set: (value) => !value && emit("close"),
});
const members = ref<Candidate[] | null>(null);
const search = ref("");
const chosen = ref<Candidate | null>(null);
const givenOn = ref(todayIso());
const comment = ref("");
const busy = ref(false);

const shown = computed(() => {
  const needle = search.value.trim().toLowerCase();
  return (members.value ?? []).filter((m) => !needle || m.name.toLowerCase().includes(needle));
});

/* Picking a member writes their name into the search box and closes the list; editing the box again drops the choice. */
function pick(member: Candidate): void {
  chosen.value = member;
  search.value = member.name;
}

watch(search, (text) => {
  if (chosen.value && text !== chosen.value.name) {
    chosen.value = null;
  }
});

watch(
  () => props.keyToAssign,
  async (key) => {
    if (!key) {
      return;
    }
    search.value = "";
    chosen.value = null;
    givenOn.value = todayIso();
    comment.value = "";
    members.value = null;
    try {
      members.value = candidates((await membersApi.list()).members, props.keys);
    } catch (e) {
      emit("failed", `Adhérents illisibles : ${errorText(e)}`);
    }
  },
);

async function submit(): Promise<void> {
  const key = props.keyToAssign;
  if (!key || !chosen.value) {
    return;
  }
  busy.value = true;
  try {
    await keysApi.assign(key.id, { user_id: chosen.value.user_id, given_on: givenOn.value, comment: comment.value });
    emit("done", `✅ Clé « ${key.code} » remise à ${chosen.value.name}.`);
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
  <UiDialog v-model:open="open" :title="`🔑 Remettre la clé « ${keyToAssign?.code} »`" data-testid="key-assign-dialog">
    <form novalidate @submit.prevent="submit">
      <label for="assign-search" :class="label">Adhérent de la saison *</label>
      <input
        id="assign-search"
        v-model="search"
        type="search"
        data-testid="assign-search"
        placeholder="Rechercher un nom…"
        :class="field"
      />
      <ul v-if="!chosen" class="mt-2 max-h-56 overflow-y-auto rounded-lg border border-slate-200">
        <li v-if="!members" class="px-2.5 py-2 text-xs text-slate-500">Chargement des adhérents…</li>
        <li v-else-if="!shown.length" class="px-2.5 py-2 text-xs text-slate-500">Aucun adhérent trouvé.</li>
        <li v-for="m in shown" :key="m.user_id">
          <button
            type="button"
            data-testid="assign-member"
            :disabled="m.heldCode !== null"
            class="w-full cursor-pointer px-2.5 py-1.5 text-left text-[13px] hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
            @click="pick(m)"
          >
            {{ m.name }}
            <template v-if="m.heldCode">— détient déjà la clé {{ m.heldCode }}</template>
          </button>
        </li>
      </ul>
      <div class="mt-3">
        <label for="assign-date" :class="label">Remise le *</label>
        <input id="assign-date" v-model="givenOn" type="date" required data-testid="assign-date" :class="field" />
      </div>
      <div class="mt-3">
        <label for="assign-comment" :class="label">Commentaire</label>
        <textarea id="assign-comment" v-model="comment" rows="3" maxlength="500" data-testid="assign-comment" :class="field" />
      </div>
      <UiDialogActions class="mt-4">
        <UiButton variant="muted" @click="open = false">Annuler</UiButton>
        <UiButton type="submit" :disabled="!chosen || !givenOn" :busy="busy && 'Enregistrement…'" data-testid="assign-submit">
          Remettre la clé
        </UiButton>
      </UiDialogActions>
    </form>
  </UiDialog>
</template>
