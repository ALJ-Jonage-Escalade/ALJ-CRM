<script setup lang="ts">
/* Attach of a HelloAsso registration to a member picked by hand (a parent registered their child under their own
   name): search among every member of the base, then the comment the attach requires. A member who already has a
   HelloAsso membership this season, or several manual ones, is listed but cannot be picked. */
import { computed, ref } from "vue";
import { canReceive, memberOptionLabel, searchMembers, type MembershipMember } from "./helloassoImport";

const props = defineProps<{
  members: readonly MembershipMember[];
  memberId: number | null;
  comment: string;
  person: string; // the HelloAsso name of the registration
  cancellable: boolean;
}>();
const emit = defineEmits<{ pick: [memberId: number | null]; comment: [text: string]; cancel: [] }>();

const query = ref("");
const results = computed(() => searchMembers(props.members, query.value));
const chosen = computed(() => props.members.find((member) => member.user_id === props.memberId));
</script>

<template>
  <div class="mt-1 rounded-md border border-blue-200 bg-blue-50 p-1.5 text-slate-700">
    <div class="mb-1 flex items-center justify-between gap-2 font-semibold text-blue-800">
      🔗 Rattacher à un adhérent
      <button
        v-if="cancellable"
        type="button"
        data-testid="ha-attach-cancel"
        :aria-label="`Annuler le rattachement de ${person}`"
        title="Annuler le rattachement"
        class="rounded px-1 text-slate-500 hover:bg-blue-100"
        @click="emit('cancel')"
      >
        ✕
      </button>
    </div>
    <div v-if="chosen" data-testid="ha-attach-chosen" class="mb-1 font-semibold">
      {{ memberOptionLabel(chosen) }}
      <button type="button" data-testid="ha-attach-change" class="ml-1 font-normal text-blue-700 underline" @click="emit('pick', null)">
        changer
      </button>
    </div>
    <template v-else>
      <input
        v-model="query"
        type="search"
        data-testid="ha-attach-search"
        :aria-label="`Adhérent à qui rattacher l'inscription de ${person}`"
        placeholder="🔍 Nom, prénom ou licence…"
        class="mb-1 block w-full rounded-md border border-slate-300 bg-white px-1.5 py-1 text-xs"
      />
      <ul v-if="results.length" class="mb-1 flex flex-col gap-0.5">
        <li v-for="member in results" :key="member.user_id">
          <button
            type="button"
            data-testid="ha-attach-option"
            :disabled="!canReceive(member)"
            class="w-full rounded px-1.5 py-0.5 text-left hover:bg-blue-100 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent"
            @click="emit('pick', member.user_id)"
          >
            {{ memberOptionLabel(member) }}
          </button>
        </li>
      </ul>
      <p v-else-if="query.trim()" class="mb-1 text-slate-500">Aucun adhérent trouvé.</p>
    </template>
    <textarea
      data-testid="ha-attach-comment"
      :value="comment"
      rows="2"
      maxlength="1000"
      :aria-label="`Commentaire du rattachement de ${person}`"
      placeholder="Commentaire (obligatoire) : pourquoi ce rattachement ?"
      class="block w-full rounded-md border border-slate-300 bg-white px-1.5 py-1 text-xs"
      @input="emit('comment', ($event.target as HTMLTextAreaElement).value)"
    ></textarea>
  </div>
</template>
