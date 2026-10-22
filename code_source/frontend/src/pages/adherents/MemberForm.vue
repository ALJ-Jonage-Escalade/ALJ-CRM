<script setup lang="ts">
/* Edit or add form of a member record (admins). Checked when submitted (draftErrors): each problem is shown under
   its field and the first invalid field gets the focus; the form emits save only when every field is valid.
   adding: identity, birth date, amount and emergency contact are asked too. The tariff the member already has stays
   among the choices. */
import { computed, nextTick, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import { draftErrors, STATUS_CHOICES, withDateTag, type DraftErrors, type DraftField, type MemberDraft, type TarifChoice } from "./record";

const draft = defineModel<MemberDraft>({ required: true });
const props = defineProps<{ adding: boolean; tarifs: readonly TarifChoice[]; saving?: boolean; today?: Date }>();
const emit = defineEmits<{ save: []; cancel: [] }>();

const errors = ref<DraftErrors>({});
// A corrected field loses its message at once; the others wait for the next submit
watch(
  draft,
  (d) => {
    const now = draftErrors(d, props.adding, props.today);
    for (const field of Object.keys(errors.value) as DraftField[]) if (!now[field]) delete errors.value[field];
  },
  { deep: true },
);

const initialTarif = draft.value.tarif_name;
const tarifs = computed<TarifChoice[]>(() =>
  initialTarif && !props.tarifs.some((t) => t.tarif === initialTarif) ? [{ tarif: initialTarif, detail: "" }, ...props.tarifs] : [...props.tarifs],
);
const statuses = computed(() =>
  STATUS_CHOICES.some(([v]) => v === draft.value.status) || props.adding ? STATUS_CHOICES : [[draft.value.status, draft.value.status] as const, ...STATUS_CHOICES],
);

const root = ref<HTMLFormElement | null>(null);
async function submit(): Promise<void> {
  errors.value = draftErrors(draft.value, props.adding, props.today);
  const first = Object.keys(errors.value)[0];
  if (!first) {
    emit("save");
    return;
  }
  await nextTick();
  root.value?.querySelector<HTMLElement>(`[data-field="${first}"]`)?.focus();
}

function addDate(): void {
  draft.value.commentaires_correctif = withDateTag(draft.value.commentaires_correctif, props.today);
}

const label = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const fieldClass = (name: DraftField) => [
  "w-full rounded-lg border bg-white px-2.5 py-2 text-[13px]",
  errors.value[name] ? "border-red-500 bg-red-50" : "border-slate-300",
];
const section = "mt-1 text-xs font-bold text-slate-700";
const attrs = (name: DraftField) => ({
  id: `member-${name}`,
  "data-field": name,
  "data-testid": `member-${name}`,
  "aria-invalid": errors.value[name] ? true : undefined,
  "aria-describedby": errors.value[name] ? `member-${name}-error` : undefined,
});

const TEXT_FIELDS: { name: DraftField; label: string; type?: string; placeholder?: string; wide?: boolean; adding?: boolean }[] = [
  { name: "email_primary", label: "✉️ E-mail principal", type: "email", placeholder: "nom@example.com" },
  { name: "email_secondary", label: "✉️ E-mail secondaire", type: "email", placeholder: "deuxieme@example.com" },
  { name: "phone", label: "📞 Téléphone", type: "tel", placeholder: "06 12 34 56 78" },
  { name: "zip_code", label: "Code postal", placeholder: "69330" },
  { name: "city", label: "Ville", placeholder: "Jonage" },
  { name: "emergency1_name", label: "Contact d'urgence (nom, prénom)", placeholder: "DUPONT Pierre", adding: true },
  { name: "emergency1_phone", label: "Téléphone d'urgence", type: "tel", placeholder: "06 98 76 54 32", adding: true },
];
const textFields = computed(() => TEXT_FIELDS.filter((f) => !f.adding || props.adding));
</script>

<template>
  <form ref="root" novalidate class="flex flex-col gap-3" data-testid="member-form" @submit.prevent="submit">
    <template v-if="adding">
      <div :class="section">👤 Identité</div>
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label for="member-last_name" :class="label">Nom de famille *</label>
          <input v-model="draft.last_name" v-bind="attrs('last_name')" type="text" placeholder="DUPONT" autocomplete="off" :class="[fieldClass('last_name'), 'uppercase']">
          <p v-if="errors.last_name" id="member-last_name-error" class="mt-1 text-xs text-red-600">{{ errors.last_name }}</p>
        </div>
        <div>
          <label for="member-first_name" :class="label">Prénom *</label>
          <input v-model="draft.first_name" v-bind="attrs('first_name')" type="text" placeholder="Jean" autocomplete="off" :class="fieldClass('first_name')">
          <p v-if="errors.first_name" id="member-first_name-error" class="mt-1 text-xs text-red-600">{{ errors.first_name }}</p>
        </div>
        <div>
          <label for="member-birth_date" :class="label">Date de naissance *</label>
          <input v-model="draft.birth_date" v-bind="attrs('birth_date')" type="date" :class="fieldClass('birth_date')">
          <p v-if="errors.birth_date" id="member-birth_date-error" class="mt-1 text-xs text-red-600">{{ errors.birth_date }}</p>
        </div>
        <div>
          <label for="member-gender" :class="label">Sexe</label>
          <select v-model="draft.gender" v-bind="attrs('gender')" :class="fieldClass('gender')">
            <option value="Homme">Homme</option>
            <option value="Femme">Femme</option>
          </select>
        </div>
      </div>
    </template>

    <div :class="section">📋 Inscription</div>
    <div class="grid gap-3 sm:grid-cols-2">
      <div>
        <label for="member-status" :class="label">Statut d'inscription</label>
        <select v-model="draft.status" v-bind="attrs('status')" :class="[fieldClass('status'), 'font-semibold']">
          <option v-for="[value, text] in statuses" :key="value" :value="value">{{ text }}</option>
        </select>
      </div>
      <div v-if="adding">
        <label for="member-amount" :class="label">Montant payé (€)</label>
        <input v-model="draft.amount" v-bind="attrs('amount')" type="text" inputmode="decimal" :class="fieldClass('amount')">
        <p v-if="errors.amount" id="member-amount-error" class="mt-1 text-xs text-red-600">{{ errors.amount }}</p>
      </div>
    </div>
    <fieldset>
      <legend :class="label">Groupe (tarif HelloAsso) *</legend>
      <div
        role="radiogroup"
        data-testid="member-tarifs"
        :class="['flex max-h-44 flex-col gap-1 overflow-y-auto rounded-lg border bg-slate-50 p-1.5', errors.tarif_name ? 'border-red-500' : 'border-slate-300']"
      >
        <label
          v-for="(t, i) in tarifs"
          :key="t.tarif"
          :class="['flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs', draft.tarif_name === t.tarif ? 'border-accent bg-blue-50' : 'border-transparent bg-white']"
        >
          <input v-model="draft.tarif_name" type="radio" name="member-tarif" :value="t.tarif" :data-field="i === 0 ? 'tarif_name' : undefined" class="accent-accent">
          <span class="min-w-0">
            <b class="block font-semibold text-slate-800">{{ t.tarif }}</b>
            <span v-if="t.detail" class="block text-[11px] text-slate-500">{{ t.detail }}</span>
          </span>
        </label>
        <span v-if="!tarifs.length" class="p-2 text-[11.5px] text-slate-500">Aucun tarif disponible pour cette saison.</span>
      </div>
      <p v-if="errors.tarif_name" class="mt-1 text-xs text-red-600" data-testid="member-tarif-error">{{ errors.tarif_name }}</p>
    </fieldset>

    <div :class="section">🧗 Badges & licence FFME</div>
    <div class="grid gap-3 sm:grid-cols-3">
      <div>
        <label for="member-licence_ffme" :class="label">N° licence FFME</label>
        <input v-model="draft.licence_ffme" v-bind="attrs('licence_ffme')" type="text" placeholder="123456" :class="fieldClass('licence_ffme')">
      </div>
      <div>
        <label for="member-badge_rouge" :class="label">🔴 Badge rouge diff</label>
        <select v-model="draft.badge_rouge" v-bind="attrs('badge_rouge')" :class="fieldClass('badge_rouge')">
          <option value="Non">Non</option>
          <option value="Oui">Oui</option>
        </select>
      </div>
      <div>
        <label for="member-autonomie_bloc" :class="label">🧗 Autonomie bloc</label>
        <select v-model="draft.autonomie_bloc" v-bind="attrs('autonomie_bloc')" :class="fieldClass('autonomie_bloc')">
          <option value="Non">Non</option>
          <option value="Oui">Oui</option>
        </select>
      </div>
    </div>

    <div :class="section">📞 Coordonnées</div>
    <div>
      <label for="member-address" :class="label">📍 Adresse (n° et rue)</label>
      <!-- textarea: stored addresses can span several lines, which an <input> would merge on save -->
      <textarea v-model="draft.address" v-bind="attrs('address')" rows="2" placeholder="12 rue de la Paix" :class="fieldClass('address')" />
    </div>
    <div class="grid gap-3 sm:grid-cols-2">
      <div v-for="f in textFields" :key="f.name">
        <label :for="`member-${f.name}`" :class="label">{{ f.label }}</label>
        <input v-model="draft[f.name]" v-bind="attrs(f.name)" :type="f.type ?? 'text'" :placeholder="f.placeholder" :class="fieldClass(f.name)">
        <p v-if="errors[f.name]" :id="`member-${f.name}-error`" class="mt-1 text-xs text-red-600">{{ errors[f.name] }}</p>
      </div>
    </div>

    <div class="flex items-center justify-between">
      <label for="member-commentaires_correctif" :class="[label, 'mb-0']">💬 Commentaire / notes</label>
      <UiButton variant="muted" small data-testid="member-comment-date" title="Insérer la date du jour" @click="addDate">📅 Date</UiButton>
    </div>
    <textarea
      v-model="draft.commentaires_correctif"
      v-bind="attrs('commentaires_correctif')"
      rows="3"
      placeholder="Note interne (certificat médical papier remis, dispense…)"
      :class="fieldClass('commentaires_correctif')"
    />

    <div class="sticky bottom-0 -mx-5 -mb-5 flex justify-end gap-2 border-t border-slate-200 bg-white px-5 py-3">
      <UiButton variant="muted" data-testid="member-cancel" @click="emit('cancel')">Annuler</UiButton>
      <UiButton type="submit" data-testid="member-save" :busy="saving && (adding ? 'Création…' : 'Enregistrement…')">
        {{ adding ? "➕ Créer l'adhérent" : "💾 Enregistrer" }}
      </UiButton>
    </div>
  </form>
</template>
