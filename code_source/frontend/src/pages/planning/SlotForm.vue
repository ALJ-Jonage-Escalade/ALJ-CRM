<script setup lang="ts">
/* Fields of a slot (create or edit). Checked before saving (slotError): the form emits save, or invalid with the
   message to show. The day, type and tariffs a slot already has stay among the choices, so saving it keeps them. */
import { computed } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { dayOptions, slotError, tarifOptions, typeOptions, type SlotDraft } from "./slots";

const draft = defineModel<SlotDraft>({ required: true });
const props = defineProps<{ tarifs: readonly string[]; saving?: boolean }>();
const emit = defineEmits<{ save: []; invalid: [message: string]; cancel: [] }>();

const days = computed(() => dayOptions(draft.value.jour));
const types = computed(() => typeOptions(draft.value.type));
// The tariffs linked when the form opens: unticking one the season no longer has keeps it in the list
const linked = [...draft.value.helloasso_tarifs];
const tarifs = computed(() => tarifOptions(props.tarifs, linked));

function submit(): void {
  const error = slotError(draft.value);
  if (error) {
    emit("invalid", error);
  } else {
    emit("save");
  }
}

const label = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const field = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]";
</script>

<template>
  <form novalidate class="flex flex-col gap-3" @submit.prevent="submit">
    <div>
      <label for="slot-groupe" :class="label">Nom du groupe *</label>
      <input
        id="slot-groupe"
        v-model="draft.groupe"
        type="text"
        data-testid="slot-groupe"
        placeholder="Ex : Loisir collège - lundi 18h30"
        :class="field"
      />
    </div>
    <div class="grid gap-3 sm:grid-cols-2">
      <div>
        <label for="slot-jour" :class="label">Jour *</label>
        <select id="slot-jour" v-model="draft.jour" data-testid="slot-jour" :class="field">
          <option v-for="day in days" :key="day" :value="day">{{ day }}</option>
        </select>
      </div>
      <div>
        <label for="slot-horaires" :class="label">Horaires * (ex : 18:00 - 20:00)</label>
        <input
          id="slot-horaires"
          v-model="draft.horaires"
          type="text"
          data-testid="slot-horaires"
          placeholder="18:00 - 20:00"
          :class="field"
        />
      </div>
      <div>
        <label for="slot-type" :class="label">Type de groupe</label>
        <select id="slot-type" v-model="draft.type" data-testid="slot-type" :class="field">
          <option v-for="[value, text] in types" :key="value" :value="value">{{ text }}</option>
        </select>
      </div>
      <div>
        <label for="slot-categorie" :class="label">Catégorie d'âge</label>
        <input
          id="slot-categorie"
          v-model="draft.categorie_age"
          type="text"
          data-testid="slot-categorie"
          placeholder="Ex : U11-U13, Collège, Adultes…"
          :class="field"
        />
      </div>
    </div>
    <div>
      <label for="slot-encadrants" :class="label">Encadrant(s) (séparés par des virgules)</label>
      <input
        id="slot-encadrants"
        v-model="draft.encadrants"
        type="text"
        data-testid="slot-encadrants"
        placeholder="Ex : Antoine GAUTHIER, Rodolphe JULLIEN"
        :class="field"
      />
    </div>
    <div>
      <label for="slot-whatsapp" :class="label">Lien d'invitation WhatsApp (optionnel)</label>
      <input
        id="slot-whatsapp"
        v-model="draft.whatsapp_link"
        type="url"
        data-testid="slot-whatsapp"
        placeholder="https://chat.whatsapp.com/…"
        :class="field"
      />
    </div>
    <fieldset>
      <legend :class="label">Tarifs HelloAsso associés (cocher les tarifs de la campagne)</legend>
      <div
        data-testid="slot-tarifs"
        class="flex max-h-32 flex-col gap-1 overflow-y-auto rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-2"
      >
        <label v-for="tarif in tarifs" :key="tarif" class="flex cursor-pointer items-center gap-2 text-xs">
          <input v-model="draft.helloasso_tarifs" type="checkbox" :value="tarif" />
          <span>{{ tarif }}</span>
        </label>
        <span v-if="!tarifs.length" class="text-[11.5px] text-slate-500">
          Aucun tarif de saison configuré. Saisissez le tarif dans le nom de groupe.
        </span>
      </div>
    </fieldset>
    <div class="grid grid-cols-2 gap-3">
      <div>
        <label for="slot-naissance-min" :class="label">Année naissance min</label>
        <input
          id="slot-naissance-min"
          v-model="draft.naissance_min"
          type="text"
          inputmode="numeric"
          data-testid="slot-naissance-min"
          placeholder="2015"
          :class="field"
        />
      </div>
      <div>
        <label for="slot-naissance-max" :class="label">Année naissance max</label>
        <input
          id="slot-naissance-max"
          v-model="draft.naissance_max"
          type="text"
          inputmode="numeric"
          data-testid="slot-naissance-max"
          placeholder="2018"
          :class="field"
        />
      </div>
    </div>
    <UiDialogActions class="mt-1 border-t border-slate-100 pt-3">
      <UiButton variant="muted" data-testid="slot-cancel" @click="emit('cancel')">Annuler</UiButton>
      <UiButton type="submit" :busy="saving && 'Enregistrement…'" data-testid="slot-save">💾 Enregistrer le créneau</UiButton>
    </UiDialogActions>
  </form>
</template>
