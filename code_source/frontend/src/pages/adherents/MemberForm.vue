<script setup lang="ts">
/* Edit or add form of a member record (admins). Checked when submitted (draftErrors): each problem is shown under
   its field and the first invalid field gets the focus; the form emits save only when every field is valid.
   adding: identity, birth date and amount are asked too. The tariff the member already has stays
   among the choices. */
import { computed, nextTick, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { SEX_LABELS, SEX_NOT_GIVEN, type Sex } from "../../lib/sex";
import {
  contactPhoneField,
  draftErrors,
  newContactRow,
  STATUS_CHOICES,
  withDateTag,
  type DraftErrors,
  type DraftField,
  type MemberDraft,
  type TarifChoice,
  type TextField,
} from "./record";

const draft = defineModel<MemberDraft>({ required: true });
const props = defineProps<{ adding: boolean; tarifs: readonly TarifChoice[]; saving?: boolean; today?: Date }>();
const emit = defineEmits<{ save: []; cancel: [] }>();

const errors = ref<DraftErrors>({});
const initialAmount = draft.value.amount;
// A corrected field loses its message at once; the others wait for the next submit
watch(
  draft,
  (d) => {
    const now = draftErrors(d, props.adding, props.today, initialAmount);
    for (const field of Object.keys(errors.value) as DraftField[]) {
      if (!now[field]) {
        delete errors.value[field];
      }
    }
  },
  { deep: true },
);

const initialTarif = draft.value.tarif_name;
const tarifs = computed<TarifChoice[]>(() =>
  initialTarif && !props.tarifs.some((t) => t.tarif === initialTarif)
    ? [{ tarif: initialTarif, detail: "" }, ...props.tarifs]
    : [...props.tarifs],
);
const statuses = computed(() =>
  STATUS_CHOICES.some(([v]) => v === draft.value.status) || props.adding
    ? STATUS_CHOICES
    : [[draft.value.status, draft.value.status] as const, ...STATUS_CHOICES],
);
const sexes = Object.entries(SEX_LABELS) as [Sex, string][];

const root = ref<HTMLFormElement | null>(null);
async function submit(): Promise<void> {
  errors.value = draftErrors(draft.value, props.adding, props.today, initialAmount);
  const first = Object.keys(errors.value)[0];
  if (!first) {
    emit("save");
    return;
  }
  await nextTick();
  root.value?.querySelector<HTMLElement>(`[data-field="${first}"]`)?.focus();
}

function focusInContact(key: number, ...testIds: string[]): void {
  const row = root.value?.querySelector(`[data-contact-key="${key}"]`);
  for (const testId of testIds) {
    const element = row?.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
    if (element) {
      element.focus();
      return;
    }
  }
}

async function addContact(): Promise<void> {
  const row = newContactRow();
  draft.value.emergency_contacts.push(row);
  await nextTick();
  focusInContact(row.key, "contact-name");
}

/** Moves a row one place; the focus stays on the button pressed, or on the other arrow when that one is gone. */
async function moveContact(index: number, step: -1 | 1): Promise<void> {
  const rows = draft.value.emergency_contacts;
  const [row] = rows.splice(index, 1);
  if (!row) {
    return;
  }
  rows.splice(index + step, 0, row);
  await nextTick();
  const pressed = step < 0 ? "contact-up" : "contact-down";
  focusInContact(row.key, pressed, step < 0 ? "contact-down" : "contact-up");
}

async function removeContact(index: number): Promise<void> {
  draft.value.emergency_contacts.splice(index, 1);
  await nextTick();
  root.value?.querySelector<HTMLElement>('[data-testid="contact-add"]')?.focus();
}

function addDate(): void {
  draft.value.commentaires_correctif = withDateTag(draft.value.commentaires_correctif, props.today);
}

const label = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const fieldBase = "w-full rounded-lg border bg-white px-2.5 py-2 text-[13px]";
const fieldClass = (name: DraftField) => [fieldBase, errors.value[name] ? "border-red-500 bg-red-50" : "border-slate-300"];
const section = "mt-1 text-xs font-bold text-slate-700";
const attrs = (name: DraftField) => ({
  id: `member-${name}`,
  "data-field": name,
  "data-testid": `member-${name}`,
  "aria-invalid": errors.value[name] ? true : undefined,
  "aria-describedby": errors.value[name] ? `member-${name}-error` : undefined,
});

const TEXT_FIELDS: { name: TextField; label: string; type?: string; placeholder?: string }[] = [
  { name: "email_primary", label: "✉️ E-mail principal", type: "email", placeholder: "nom@example.com" },
  { name: "email_secondary", label: "✉️ E-mail secondaire", type: "email", placeholder: "deuxieme@example.com" },
  { name: "phone", label: "📞 Téléphone", type: "tel", placeholder: "06 12 34 56 78" },
  { name: "zip_code", label: "Code postal", placeholder: "69330" },
  { name: "city", label: "Ville", placeholder: "Jonage" },
];
</script>

<template>
  <form ref="root" novalidate class="flex flex-col gap-3" data-testid="member-form" @submit.prevent="submit">
    <div :class="section">👤 Identité</div>
    <div class="grid gap-3 sm:grid-cols-2">
      <div>
        <label for="member-last_name" :class="label">Nom de famille *</label>
        <input
          v-model="draft.last_name"
          v-bind="attrs('last_name')"
          type="text"
          placeholder="DUPONT"
          autocomplete="off"
          :class="[fieldClass('last_name'), 'uppercase']"
        />
        <p v-if="errors.last_name" id="member-last_name-error" class="mt-1 text-xs text-red-600">{{ errors.last_name }}</p>
      </div>
      <div>
        <label for="member-first_name" :class="label">Prénom *</label>
        <input
          v-model="draft.first_name"
          v-bind="attrs('first_name')"
          type="text"
          placeholder="Jean"
          autocomplete="off"
          :class="fieldClass('first_name')"
        />
        <p v-if="errors.first_name" id="member-first_name-error" class="mt-1 text-xs text-red-600">{{ errors.first_name }}</p>
      </div>
      <div>
        <label for="member-birth_date" :class="label">Date de naissance {{ adding ? "*" : "" }}</label>
        <input v-model="draft.birth_date" v-bind="attrs('birth_date')" type="date" :class="fieldClass('birth_date')" />
        <p v-if="errors.birth_date" id="member-birth_date-error" class="mt-1 text-xs text-red-600">{{ errors.birth_date }}</p>
      </div>
    </div>

    <div :class="section">📋 Inscription</div>
    <div class="grid gap-3 sm:grid-cols-2">
      <div>
        <label for="member-status" :class="label">Statut d'inscription</label>
        <select v-model="draft.status" v-bind="attrs('status')" :class="[fieldClass('status'), 'font-semibold']">
          <option v-for="[value, text] in statuses" :key="value" :value="value">{{ text }}</option>
        </select>
      </div>
      <div>
        <label for="member-amount" :class="label">Montant payé (€)</label>
        <input v-model="draft.amount" v-bind="attrs('amount')" type="text" inputmode="decimal" :class="fieldClass('amount')" />
        <p v-if="errors.amount" id="member-amount-error" class="mt-1 text-xs text-red-600">{{ errors.amount }}</p>
      </div>
    </div>
    <fieldset>
      <legend :class="label">Groupe (tarif HelloAsso) *</legend>
      <div
        role="radiogroup"
        data-testid="member-tarifs"
        :class="[
          'flex max-h-44 flex-col gap-1 overflow-y-auto rounded-lg border bg-slate-50 p-1.5',
          errors.tarif_name ? 'border-red-500' : 'border-slate-300',
        ]"
      >
        <label
          v-for="(t, i) in tarifs"
          :key="t.tarif"
          :class="[
            'flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs',
            draft.tarif_name === t.tarif ? 'border-accent bg-blue-50' : 'border-transparent bg-white',
          ]"
        >
          <input
            v-model="draft.tarif_name"
            type="radio"
            name="member-tarif"
            :value="t.tarif"
            :data-field="i === 0 ? 'tarif_name' : undefined"
            class="accent-accent"
          />
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
    <div class="grid gap-3 sm:grid-cols-2">
      <div>
        <label for="member-licence_ffme" :class="label">N° licence FFME</label>
        <input
          v-model="draft.licence_ffme"
          v-bind="attrs('licence_ffme')"
          type="text"
          placeholder="123456"
          :class="fieldClass('licence_ffme')"
        />
      </div>
      <div>
        <label for="member-sex" :class="label">Sexe (FFME)</label>
        <select v-model="draft.sex" v-bind="attrs('sex')" :class="fieldClass('sex')">
          <option value="">{{ SEX_NOT_GIVEN }}</option>
          <option v-for="[value, text] in sexes" :key="value" :value="value">{{ text }}</option>
        </select>
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
      <div>
        <label for="member-photo_auth" :class="label">📷 Droit à l'image</label>
        <select v-model="draft.photo_auth" v-bind="attrs('photo_auth')" :class="fieldClass('photo_auth')">
          <option value="Oui">Oui</option>
          <option value="Non">Non</option>
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
      <div v-for="f in TEXT_FIELDS" :key="f.name">
        <label :for="`member-${f.name}`" :class="label">{{ f.label }}</label>
        <input
          v-model="draft[f.name]"
          v-bind="attrs(f.name)"
          :type="f.type ?? 'text'"
          :placeholder="f.placeholder"
          :class="fieldClass(f.name)"
        />
        <p v-if="errors[f.name]" :id="`member-${f.name}-error`" class="mt-1 text-xs text-red-600">{{ errors[f.name] }}</p>
      </div>
    </div>

    <div :class="section">🚨 Contacts d'urgence</div>
    <div class="flex flex-col gap-3" data-testid="contact-list">
      <div
        v-for="(contact, index) in draft.emergency_contacts"
        :key="contact.key"
        :data-contact-key="contact.key"
        data-testid="contact-row"
        class="rounded-lg border border-slate-200 bg-slate-50 p-2.5"
      >
        <div class="mb-2 flex items-center justify-between gap-2">
          <span data-testid="contact-label" class="text-xs font-bold text-slate-700">
            {{ index === 0 ? "Principal" : `Contact ${index + 1}` }}
          </span>
          <div class="flex gap-1">
            <UiButton
              v-if="index > 0"
              variant="muted"
              small
              data-testid="contact-up"
              :aria-label="`Monter le contact ${index + 1}`"
              @click="moveContact(index, -1)"
            >
              ↑
            </UiButton>
            <UiButton
              v-if="index < draft.emergency_contacts.length - 1"
              variant="muted"
              small
              data-testid="contact-down"
              :aria-label="`Descendre le contact ${index + 1}`"
              @click="moveContact(index, 1)"
            >
              ↓
            </UiButton>
            <UiButton
              variant="danger"
              small
              data-testid="contact-remove"
              :aria-label="`Supprimer le contact ${index + 1}`"
              @click="removeContact(index)"
            >
              🗑
            </UiButton>
          </div>
        </div>
        <div class="grid gap-3 sm:grid-cols-2">
          <div>
            <label :for="`member-contact_name_${contact.key}`" :class="label">Nom, prénom</label>
            <input
              :id="`member-contact_name_${contact.key}`"
              v-model="contact.name"
              data-testid="contact-name"
              type="text"
              placeholder="DUPONT Pierre"
              :class="[fieldBase, 'border-slate-300']"
            />
          </div>
          <div>
            <label :for="`member-${contactPhoneField(contact.key)}`" :class="label">Téléphone</label>
            <input
              v-model="contact.phone"
              v-bind="attrs(contactPhoneField(contact.key))"
              data-testid="contact-phone"
              type="tel"
              placeholder="06 98 76 54 32"
              :class="fieldClass(contactPhoneField(contact.key))"
            />
            <p
              v-if="errors[contactPhoneField(contact.key)]"
              :id="`member-${contactPhoneField(contact.key)}-error`"
              class="mt-1 text-xs text-red-600"
            >
              {{ errors[contactPhoneField(contact.key)] }}
            </p>
          </div>
        </div>
      </div>
      <p v-if="!draft.emergency_contacts.length" class="text-xs text-slate-500" data-testid="contact-none">Aucun contact d'urgence.</p>
      <div>
        <UiButton variant="muted" small data-testid="contact-add" @click="addContact">➕ Ajouter un contact</UiButton>
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

    <UiDialogActions class="sticky bottom-0 -mx-5 -mb-5 border-t border-slate-200 bg-white px-5 py-3">
      <UiButton variant="muted" data-testid="member-cancel" @click="emit('cancel')">Annuler</UiButton>
      <UiButton type="submit" data-testid="member-save" :busy="saving && (adding ? 'Création…' : 'Enregistrement…')">
        {{ adding ? "➕ Créer l'adhérent" : "💾 Enregistrer" }}
      </UiButton>
    </UiDialogActions>
  </form>
</template>
