<script setup lang="ts">
import { computed, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";

const props = defineProps<{
  competitionId: number;
  canWrite: boolean;
}>();

export interface Programme {
  accueil: string;
  qualifications: string;
  finales: string;
  podiums: string;
  notes: string;
}

const STORAGE_KEY = computed(() => `alj_comp_prog_${props.competitionId}`);

const programme = ref<Programme>({
  accueil: "08h30 - 09h00 : Accueil & pointage des athlètes",
  qualifications: "09h30 - 13h30 : Vague de qualifications",
  finales: "15h00 - 17h00 : Finales par catégorie",
  podiums: "17h30 : Cérémonie de remise des prix & podiums",
  notes: "",
});

function load(): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY.value);
    if (raw) {
      programme.value = JSON.parse(raw);
    }
  } catch {
    // Keep default
  }
}

watch(() => props.competitionId, load, { immediate: true });

function saveProgramme(): void {
  localStorage.setItem(STORAGE_KEY.value, JSON.stringify(programme.value));
}

const editing = ref(false);
const draft = ref<Programme>({ ...programme.value });

function openEdit(): void {
  draft.value = { ...programme.value };
  editing.value = true;
}

function submitEdit(): void {
  programme.value = { ...draft.value };
  saveProgramme();
  editing.value = false;
}

const field = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs";
const label = "mb-1 block text-xs font-semibold text-slate-700";
</script>

<template>
  <div class="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="programme-section">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
      <div>
        <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5">⏱️ Programme et horaires</h3>
        <p class="text-xs text-slate-500">Planning prévisionnel de la journée de compétition.</p>
      </div>
      <UiButton v-if="canWrite" variant="muted" small data-testid="edit-programme-btn" @click="openEdit">✏️ Modifier le programme</UiButton>
    </div>

    <div class="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
      <div class="rounded-lg border border-blue-100 bg-blue-50/50 p-2.5 text-xs">
        <span class="block font-bold text-blue-900 mb-0.5">☕ Accueil & Pointage</span>
        <span class="text-slate-700 font-medium">{{ programme.accueil || "Non renseigné" }}</span>
      </div>
      <div class="rounded-lg border border-purple-100 bg-purple-50/50 p-2.5 text-xs">
        <span class="block font-bold text-purple-900 mb-0.5">🧗 Qualifications</span>
        <span class="text-slate-700 font-medium">{{ programme.qualifications || "Non renseigné" }}</span>
      </div>
      <div class="rounded-lg border border-amber-100 bg-amber-50/50 p-2.5 text-xs">
        <span class="block font-bold text-amber-900 mb-0.5">🔥 Finales</span>
        <span class="text-slate-700 font-medium">{{ programme.finales || "Non renseigné" }}</span>
      </div>
      <div class="rounded-lg border border-emerald-100 bg-emerald-50/50 p-2.5 text-xs">
        <span class="block font-bold text-emerald-900 mb-0.5">🏆 Remise des prix</span>
        <span class="text-slate-700 font-medium">{{ programme.podiums || "Non renseigné" }}</span>
      </div>
    </div>
    <div v-if="programme.notes" class="mt-2.5 text-xs text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-200">
      <b>Informations complémentaires :</b>
      {{ programme.notes }}
    </div>

    <!-- Modal d'édition du programme -->
    <UiDialog v-model:open="editing" title="⏱️ Modifier le programme de la compétition" data-testid="programme-dialog">
      <form class="flex flex-col gap-2.5" @submit.prevent="submitEdit">
        <div>
          <label :class="label">Heure d'accueil / pointage</label>
          <input v-model="draft.accueil" :class="field" placeholder="ex. 08h30 - 09h00 : Accueil" />
        </div>
        <div>
          <label :class="label">Début des qualifications</label>
          <input v-model="draft.qualifications" :class="field" placeholder="ex. 09h30 - 13h30 : Qualifications" />
        </div>
        <div>
          <label :class="label">Heure des finales</label>
          <input v-model="draft.finales" :class="field" placeholder="ex. 15h00 - 17h00 : Finales" />
        </div>
        <div>
          <label :class="label">Remise des prix</label>
          <input v-model="draft.podiums" :class="field" placeholder="ex. 17h30 : Podiums" />
        </div>
        <div>
          <label :class="label">Remarques / consignes d'organisation</label>
          <textarea v-model="draft.notes" rows="2" :class="field" placeholder="ex. Prévoir un pique-nique pour midi…" />
        </div>
        <UiDialogActions>
          <UiButton variant="muted" @click="editing = false">Annuler</UiButton>
          <UiButton type="submit">Enregistrer le programme</UiButton>
        </UiDialogActions>
      </form>
    </UiDialog>
  </div>
</template>
