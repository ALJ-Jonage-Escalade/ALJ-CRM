<script setup lang="ts">
import { computed, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";

const props = defineProps<{
  competitionId: number;
}>();

export interface Proposition {
  id: string;
  conducteur: string;
  places: number;
  lieu_depart: string;
  heure_depart: string;
  telephone: string;
}

export interface Demande {
  id: string;
  passager: string;
  places: number;
  lieu_prise_en_charge: string;
  telephone: string;
}

const STORAGE_KEY_PROPOSITIONS = computed(() => `alj_covoit_prop_${props.competitionId}`);
const STORAGE_KEY_DEMANDES = computed(() => `alj_covoit_dem_${props.competitionId}`);

const propositions = ref<Proposition[]>([]);
const demandes = ref<Demande[]>([]);

function load(): void {
  try {
    const rawProp = localStorage.getItem(STORAGE_KEY_PROPOSITIONS.value);
    propositions.value = rawProp ? JSON.parse(rawProp) : [];
  } catch {
    propositions.value = [];
  }
  try {
    const rawDem = localStorage.getItem(STORAGE_KEY_DEMANDES.value);
    demandes.value = rawDem ? JSON.parse(rawDem) : [];
  } catch {
    demandes.value = [];
  }
}

watch(() => props.competitionId, load, { immediate: true });

function savePropositions(): void {
  localStorage.setItem(STORAGE_KEY_PROPOSITIONS.value, JSON.stringify(propositions.value));
}

function saveDemandes(): void {
  localStorage.setItem(STORAGE_KEY_DEMANDES.value, JSON.stringify(demandes.value));
}

// Modal Proposer
const proposing = ref(false);
const draftProp = ref({
  conducteur: "",
  places: 3,
  lieu_depart: "",
  heure_depart: "",
  telephone: "",
});

function submitProposition(): void {
  if (!draftProp.value.conducteur.trim()) {
    return;
  }
  propositions.value.push({
    id: String(Date.now()),
    conducteur: draftProp.value.conducteur.trim(),
    places: Number(draftProp.value.places) || 1,
    lieu_depart: draftProp.value.lieu_depart.trim() || "Jonage",
    heure_depart: draftProp.value.heure_depart.trim() || "08h00",
    telephone: draftProp.value.telephone.trim(),
  });
  savePropositions();
  proposing.value = false;
  draftProp.value = { conducteur: "", places: 3, lieu_depart: "", heure_depart: "", telephone: "" };
}

// Modal Demander
const requesting = ref(false);
const draftDem = ref({
  passager: "",
  places: 1,
  lieu_prise_en_charge: "",
  telephone: "",
});

function submitDemande(): void {
  if (!draftDem.value.passager.trim()) {
    return;
  }
  demandes.value.push({
    id: String(Date.now()),
    passager: draftDem.value.passager.trim(),
    places: Number(draftDem.value.places) || 1,
    lieu_prise_en_charge: draftDem.value.lieu_prise_en_charge.trim() || "Jonage",
    telephone: draftDem.value.telephone.trim(),
  });
  saveDemandes();
  requesting.value = false;
  draftDem.value = { passager: "", places: 1, lieu_prise_en_charge: "", telephone: "" };
}

function removeProp(id: string): void {
  propositions.value = propositions.value.filter((p) => p.id !== id);
  savePropositions();
}

function removeDem(id: string): void {
  demandes.value = demandes.value.filter((d) => d.id !== id);
  saveDemandes();
}

const field = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs";
const label = "mb-1 block text-xs font-semibold text-slate-700";
</script>

<template>
  <div class="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="covoiturage-section">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
      <div>
        <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5">🚗 Covoiturage</h3>
        <p class="text-xs text-slate-500">Proposez ou demandez un trajet partagé entre adhérents et parents.</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <UiButton small data-testid="covoit-propose-btn" @click="proposing = true">➕ Proposer un covoiturage</UiButton>
        <UiButton variant="muted" small data-testid="covoit-demand-btn" @click="requesting = true">🙋 Demander un covoiturage</UiButton>
      </div>
    </div>

    <div class="grid gap-4 md:grid-cols-2">
      <!-- Propositions de covoiturage -->
      <div class="rounded-lg border border-slate-100 bg-slate-50/50 p-3">
        <h4 class="text-xs font-bold uppercase tracking-wide text-blue-800 mb-2 flex items-center justify-between">
          <span>🚘 Véhicules disponibles ({{ propositions.length }})</span>
        </h4>
        <div v-if="!propositions.length" class="text-xs text-slate-400 italic py-2">Aucun conducteur n'a encore proposé de places.</div>
        <div v-else class="flex flex-col gap-2">
          <div
            v-for="p in propositions"
            :key="p.id"
            class="rounded-lg border border-slate-200 bg-white p-2.5 text-xs shadow-xs flex items-start justify-between gap-2"
            data-testid="covoit-prop-card"
          >
            <div>
              <div class="font-bold text-slate-800">{{ p.conducteur }}</div>
              <div class="text-slate-600 mt-0.5">
                📍
                <b>Départ :</b>
                {{ p.lieu_depart }} à {{ p.heure_depart }}
              </div>
              <div class="text-blue-700 font-semibold mt-0.5">
                👥
                <b>{{ p.places }}</b>
                place{{ p.places > 1 ? "s" : "" }} disponible{{ p.places > 1 ? "s" : "" }}
              </div>
              <div v-if="p.telephone" class="text-slate-500 mt-0.5">
                📞
                <a :href="`tel:${p.telephone}`" class="hover:underline">{{ p.telephone }}</a>
              </div>
            </div>
            <button
              type="button"
              class="text-slate-400 hover:text-red-600 cursor-pointer p-1"
              title="Supprimer cette proposition"
              @click="removeProp(p.id)"
            >
              ✕
            </button>
          </div>
        </div>
      </div>

      <!-- Demandes de covoiturage -->
      <div class="rounded-lg border border-slate-100 bg-slate-50/50 p-3">
        <h4 class="text-xs font-bold uppercase tracking-wide text-amber-800 mb-2 flex items-center justify-between">
          <span>🙋 Passagers en recherche ({{ demandes.length }})</span>
        </h4>
        <div v-if="!demandes.length" class="text-xs text-slate-400 italic py-2">Aucune demande de covoiturage en attente.</div>
        <div v-else class="flex flex-col gap-2">
          <div
            v-for="d in demandes"
            :key="d.id"
            class="rounded-lg border border-slate-200 bg-white p-2.5 text-xs shadow-xs flex items-start justify-between gap-2"
            data-testid="covoit-dem-card"
          >
            <div>
              <div class="font-bold text-slate-800">{{ d.passager }}</div>
              <div class="text-slate-600 mt-0.5">
                📍
                <b>Prise en charge :</b>
                {{ d.lieu_prise_en_charge }}
              </div>
              <div class="text-amber-700 font-semibold mt-0.5">
                👥
                <b>{{ d.places }}</b>
                place{{ d.places > 1 ? "s" : "" }} demandée{{ d.places > 1 ? "s" : "" }}
              </div>
              <div v-if="d.telephone" class="text-slate-500 mt-0.5">
                📞
                <a :href="`tel:${d.telephone}`" class="hover:underline">{{ d.telephone }}</a>
              </div>
            </div>
            <button
              type="button"
              class="text-slate-400 hover:text-red-600 cursor-pointer p-1"
              title="Supprimer cette demande"
              @click="removeDem(d.id)"
            >
              ✕
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal Proposer -->
    <UiDialog v-model:open="proposing" title="🚗 Proposer un covoiturage" data-testid="covoit-propose-dialog">
      <form class="flex flex-col gap-2.5" @submit.prevent="submitProposition">
        <div>
          <label :class="label">Nom du conducteur *</label>
          <input v-model="draftProp.conducteur" required :class="field" placeholder="ex. Pierre Dupont" />
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label :class="label">Nombre de places *</label>
            <input v-model.number="draftProp.places" type="number" min="1" max="8" required :class="field" />
          </div>
          <div>
            <label :class="label">Heure de départ *</label>
            <input v-model="draftProp.heure_depart" required :class="field" placeholder="ex. 08h30" />
          </div>
        </div>
        <div>
          <label :class="label">Lieu de départ *</label>
          <input v-model="draftProp.lieu_depart" required :class="field" placeholder="ex. Parking Gymnase Jonage" />
        </div>
        <div>
          <label :class="label">Numéro de téléphone</label>
          <input v-model="draftProp.telephone" type="tel" :class="field" placeholder="ex. 06 12 34 56 78" />
        </div>
        <UiDialogActions>
          <UiButton variant="muted" @click="proposing = false">Annuler</UiButton>
          <UiButton type="submit">Valider la proposition</UiButton>
        </UiDialogActions>
      </form>
    </UiDialog>

    <!-- Modal Demander -->
    <UiDialog v-model:open="requesting" title="🙋 Demander un covoiturage" data-testid="covoit-demand-dialog">
      <form class="flex flex-col gap-2.5" @submit.prevent="submitDemande">
        <div>
          <label :class="label">Nom du passager *</label>
          <input v-model="draftDem.passager" required :class="field" placeholder="ex. Sophie Martin" />
        </div>
        <div>
          <label :class="label">Nombre de places demandées *</label>
          <input v-model.number="draftDem.places" type="number" min="1" max="6" required :class="field" />
        </div>
        <div>
          <label :class="label">Lieu de prise en charge souhaité *</label>
          <input v-model="draftDem.lieu_prise_en_charge" required :class="field" placeholder="ex. Jonage Centre" />
        </div>
        <div>
          <label :class="label">Numéro de téléphone</label>
          <input v-model="draftDem.telephone" type="tel" :class="field" placeholder="ex. 06 98 76 54 32" />
        </div>
        <UiDialogActions>
          <UiButton variant="muted" @click="requesting = false">Annuler</UiButton>
          <UiButton type="submit">Valider la demande</UiButton>
        </UiDialogActions>
      </form>
    </UiDialog>
  </div>
</template>
