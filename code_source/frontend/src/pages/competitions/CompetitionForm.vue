<script setup lang="ts">
/* Create or edit a competition (coaches and admins). The end date follows the start until it is set by hand;
   « Sur 2 jours » sets it to the day after. Deleting is offered when editing. */
import { computed, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import type { Schemas } from "../../lib/client";
import {
  coachChoices,
  DISCIPLINES,
  draftBody,
  draftErrors,
  draftOf,
  nextDay,
  resultsUrlHint,
  type Coach,
  type Competition,
} from "./competitions";

const props = defineProps<{ competition?: Competition; coaches: readonly Coach[]; busy: boolean }>();
const emit = defineEmits<{ save: [body: Schemas["CompetitionCreate"]]; remove: []; cancel: [] }>();

const draft = ref(draftOf(props.competition));
const shown = ref(false); // errors once the coach tried to save
const errors = computed(() => draftErrors(draft.value));
const choices = computed(() => coachChoices(props.coaches, props.competition?.coach_ids ?? []));
let endByHand = !!draft.value.date_fin;

watch(
  () => draft.value.date_competition,
  (start) => {
    if (!endByHand || (draft.value.date_fin && draft.value.date_fin < start)) {
      draft.value.date_fin = "";
    }
  },
);

function twoDays(): void {
  if (!draft.value.date_competition) {
    return;
  }
  draft.value.date_fin = nextDay(draft.value.date_competition);
  endByHand = true;
}

function save(): void {
  shown.value = true;
  if (Object.keys(errors.value).length) {
    return;
  }
  // Coaches in the order shown: the competition's own keep theirs
  const ticked = new Set(draft.value.coach_ids);
  emit("save", { ...draftBody(draft.value), coach_ids: choices.value.map((c) => c.id).filter((id) => ticked.has(id)) });
}

const label = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const field = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]";
const error = "mt-1 text-xs font-semibold text-red-600";
</script>

<template>
  <form novalidate class="grid gap-3 sm:grid-cols-2" data-testid="comp-form" @submit.prevent="save">
    <div class="sm:col-span-2">
      <label for="cf-nom" :class="label">Nom de l'épreuve *</label>
      <input id="cf-nom" v-model="draft.nom" data-testid="cf-nom" :class="field" autocomplete="off" />
      <p v-if="shown && errors.nom" :class="error" data-testid="cf-error">{{ errors.nom }}</p>
    </div>
    <div>
      <label for="cf-date" :class="label">Date de début</label>
      <input id="cf-date" v-model="draft.date_competition" type="date" data-testid="cf-date" :class="field" />
    </div>
    <div>
      <label for="cf-date-fin" :class="label">Date de fin</label>
      <div class="flex gap-1.5">
        <input
          id="cf-date-fin"
          v-model="draft.date_fin"
          type="date"
          data-testid="cf-date-fin"
          :class="field"
          :min="draft.date_competition || undefined"
          @input="endByHand = true"
        />
        <UiButton variant="muted" small data-testid="cf-two-days" :disabled="!draft.date_competition" @click="twoDays"
          >Sur 2 jours</UiButton
        >
      </div>
      <p v-if="shown && errors.date_fin" :class="error">{{ errors.date_fin }}</p>
    </div>
    <div>
      <label for="cf-lieu" :class="label">Lieu</label>
      <input id="cf-lieu" v-model="draft.lieu" data-testid="cf-lieu" :class="field" />
    </div>
    <div>
      <label for="cf-type" :class="label">Discipline</label>
      <select id="cf-type" v-model="draft.type" data-testid="cf-type" :class="field">
        <option value="">—</option>
        <option v-for="d in DISCIPLINES" :key="d" :value="d">{{ d }}</option>
        <option v-if="draft.type && !(DISCIPLINES as readonly string[]).includes(draft.type)" :value="draft.type">{{ draft.type }}</option>
      </select>
    </div>
    <div>
      <label for="cf-idffme" :class="label">N° de l'épreuve (FFME)</label>
      <input id="cf-idffme" v-model="draft.id_ffme" data-testid="cf-idffme" :class="field" />
    </div>
    <div>
      <label for="cf-prix" :class="label">Prix (€)</label>
      <input id="cf-prix" v-model="draft.prix" inputmode="decimal" data-testid="cf-prix" :class="field" placeholder="0" />
      <p v-if="shown && errors.prix" :class="error">{{ errors.prix }}</p>
    </div>
    <div class="sm:col-span-2">
      <label for="cf-whatsapp" :class="label">Groupe WhatsApp (lien)</label>
      <input
        id="cf-whatsapp"
        v-model="draft.whatsapp_link"
        type="url"
        data-testid="cf-whatsapp"
        :class="field"
        placeholder="https://chat.whatsapp.com/…"
      />
    </div>
    <div class="sm:col-span-2">
      <label for="cf-results" :class="label">Page des résultats MyCompet</label>
      <input id="cf-results" v-model="draft.url_resultats" data-testid="cf-results" :class="field" :placeholder="resultsUrlHint" />
    </div>
    <fieldset class="sm:col-span-2">
      <legend :class="label">Coachs</legend>
      <div class="flex flex-wrap gap-1.5" data-testid="cf-coaches">
        <label
          v-for="c in choices"
          :key="c.id"
          class="flex cursor-pointer items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1 text-[13px]"
        >
          <input v-model="draft.coach_ids" type="checkbox" :value="c.id" class="accent-accent" /> {{ c.nom }}
        </label>
        <span v-if="!choices.length" class="text-xs text-slate-500">Aucun coach enregistré (onglet Coachs).</span>
      </div>
    </fieldset>
    <div class="flex flex-wrap items-center gap-2 sm:col-span-2">
      <UiButton type="submit" data-testid="cf-save" :busy="busy && 'Enregistrement…'">{{
        competition ? "💾 Enregistrer" : "➕ Créer la compétition"
      }}</UiButton>
      <UiButton variant="muted" @click="emit('cancel')">Annuler</UiButton>
      <UiButton v-if="competition" variant="danger" class="ml-auto" data-testid="cf-delete" :disabled="busy" @click="emit('remove')"
        >🗑 Supprimer</UiButton
      >
    </div>
  </form>
</template>
