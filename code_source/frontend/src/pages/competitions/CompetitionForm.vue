<script setup lang="ts">
/* Create or edit a competition (coaches and admins). The end date is cleared when the start changes, unless it was
   set by hand. */
import { computed, inject, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText, type Schemas } from "../../lib/client";
import { createCompetitionsApi } from "../../services/competitions";
import {
  type Coach,
  coachChoices,
  type Competition,
  defaultDeadline,
  DISCIPLINES,
  draftBody,
  draftErrors,
  draftOf,
  resultsUrlHint,
} from "./competitions";

const props = defineProps<{ competition?: Competition; coaches: readonly Coach[]; busy: boolean }>();
const emit = defineEmits<{ save: [body: Schemas["CompetitionCreate"]]; cancel: [] }>();

const client = inject(CLIENT_KEY, null);
const competitionsApi = client ? createCompetitionsApi(client) : null;

const draft = ref(draftOf(props.competition));
const shown = ref(false); // errors once the coach tried to save
const errors = computed(() => draftErrors(draft.value));
const choices = computed(() => coachChoices(props.coaches, props.competition?.coach_ids ?? []));
const lookupBusy = ref(false);
const lookupError = ref("");
const lookupSuccess = ref("");
let endByHand = !!draft.value.date_fin;
let deadlineByHand = draft.value.deadline !== defaultDeadline(draft.value.date_competition);

function endSetByHand(): void {
  endByHand = true;
}

function deadlineSetByHand(): void {
  deadlineByHand = true;
}

watch(
  () => draft.value.date_competition,
  (start) => {
    if (!endByHand || (draft.value.date_fin && draft.value.date_fin < start)) {
      draft.value.date_fin = "";
    }
    if (!deadlineByHand && start) {
      draft.value.deadline = defaultDeadline(start);
    }
  },
);

watch(
  () => draft.value.id_ffme,
  () => {
    lookupError.value = "";
    lookupSuccess.value = "";
  },
);

async function lookupFfme(): Promise<void> {
  const num = draft.value.id_ffme?.trim();
  if (!num || !competitionsApi) {
    return;
  }
  lookupBusy.value = true;
  lookupError.value = "";
  lookupSuccess.value = "";
  try {
    const info = await competitionsApi.lookupFfme(num);
    if (info.nom) {
      draft.value.nom = info.nom;
    }
    if (info.date_competition) {
      draft.value.date_competition = info.date_competition;
      if (!deadlineByHand) {
        draft.value.deadline = defaultDeadline(info.date_competition);
      }
    }
    if (info.date_fin) {
      draft.value.date_fin = info.date_fin;
      endByHand = true;
    }
    if (info.lieu && !draft.value.lieu) {
      draft.value.lieu = info.lieu;
    }
    if (info.type && !draft.value.type) {
      draft.value.type = info.type;
    }
    lookupSuccess.value = `Titre récupéré : ${info.nom}`;
  } catch (err: unknown) {
    lookupError.value = errorText(err);
  } finally {
    lookupBusy.value = false;
  }
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
      <label for="cf-idffme" :class="label">N° de l'épreuve (FFME)</label>
      <div class="flex gap-2">
        <input id="cf-idffme" v-model="draft.id_ffme" data-testid="cf-idffme" :class="field" placeholder="ex. 18896" />
        <UiButton
          type="button"
          variant="muted"
          small
          class="shrink-0"
          data-testid="cf-lookup-btn"
          :disabled="!draft.id_ffme?.trim() || lookupBusy"
          :busy="lookupBusy && 'Recherche…'"
          @click="lookupFfme"
        >
          🔍 Récupérer le titre
        </UiButton>
      </div>
      <p v-if="lookupError" class="mt-1 text-xs font-semibold text-red-600" data-testid="cf-lookup-error">
        {{ lookupError }}
      </p>
      <p v-else-if="lookupSuccess" class="mt-1 text-xs font-semibold text-emerald-600" data-testid="cf-lookup-success">
        {{ lookupSuccess }}
      </p>
    </div>
    <div class="sm:col-span-2">
      <label for="cf-nom" :class="label">Nom de l'épreuve *</label>
      <input id="cf-nom" v-model="draft.nom" data-testid="cf-nom" :class="field" autocomplete="off" />
      <p v-if="shown && errors.nom" :class="error" data-testid="cf-error">{{ errors.nom }}</p>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:col-span-2">
      <div>
        <label for="cf-date" :class="label">Date de début</label>
        <input id="cf-date" v-model="draft.date_competition" type="date" data-testid="cf-date" :class="field" />
      </div>
      <div>
        <label for="cf-date-fin" :class="label">Date de fin</label>
        <input
          id="cf-date-fin"
          v-model="draft.date_fin"
          type="date"
          data-testid="cf-date-fin"
          :class="field"
          :min="draft.date_competition || undefined"
          @input="endSetByHand"
        />
        <p v-if="shown && errors.date_fin" :class="error">{{ errors.date_fin }}</p>
      </div>
      <div>
        <label for="cf-deadline" :class="label">Date limite (deadline)</label>
        <input id="cf-deadline" v-model="draft.deadline" type="date" data-testid="cf-deadline" :class="field" @input="deadlineSetByHand" />
      </div>
    </div>

    <details class="sm:col-span-2 rounded-lg border border-slate-200 bg-slate-50/60 p-3" data-testid="cf-details">
      <summary class="cursor-pointer text-xs font-semibold text-slate-700 select-none">📋 Informations complémentaires</summary>
      <div class="mt-3 grid gap-3">
        <div>
          <label for="cf-lieu" :class="label">Lieu</label>
          <input id="cf-lieu" v-model="draft.lieu" data-testid="cf-lieu" :class="field" />
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label for="cf-type" :class="label">Discipline</label>
            <select id="cf-type" v-model="draft.type" data-testid="cf-type" :class="field">
              <option value="">—</option>
              <option v-for="d in DISCIPLINES" :key="d" :value="d">{{ d }}</option>
              <option v-if="draft.type && !(DISCIPLINES as readonly string[]).includes(draft.type)" :value="draft.type">
                {{ draft.type }}
              </option>
            </select>
          </div>
          <div>
            <label for="cf-prix" :class="label">Prix (€)</label>
            <input id="cf-prix" v-model="draft.prix" inputmode="decimal" data-testid="cf-prix" :class="field" placeholder="0" />
            <p v-if="shown && errors.prix" :class="error">{{ errors.prix }}</p>
          </div>
        </div>
        <div>
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
        <div>
          <label for="cf-results" :class="label">Page des résultats MyCompet</label>
          <input id="cf-results" v-model="draft.url_resultats" data-testid="cf-results" :class="field" :placeholder="resultsUrlHint" />
        </div>
      </div>
    </details>

    <fieldset class="sm:col-span-2">
      <legend :class="label">Coachs</legend>
      <div class="flex flex-wrap gap-1.5" data-testid="cf-coaches">
        <label
          v-for="c in choices"
          :key="c.id"
          class="flex cursor-pointer items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1 text-[13px]"
        >
          <input v-model="draft.coach_ids" type="checkbox" :value="c.id" class="accent-accent" />
          {{ c.nom }}
        </label>
        <span v-if="!choices.length" class="text-xs text-slate-500">Aucun coach enregistré (onglet Coachs).</span>
      </div>
    </fieldset>
    <UiDialogActions class="sm:col-span-2">
      <UiButton variant="muted" @click="emit('cancel')">Annuler</UiButton>
      <UiButton type="submit" data-testid="cf-save" :busy="busy && 'Enregistrement…'">💾 Enregistrer</UiButton>
    </UiDialogActions>
  </form>
</template>
