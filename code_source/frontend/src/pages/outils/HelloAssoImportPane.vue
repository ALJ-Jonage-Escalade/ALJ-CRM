<script setup lang="ts">
/* Synchronisation of the HelloAsso membership campaign (admin): the server reads the campaign set in Paramètres and
   sorts every registration into a bucket (new, renewal, changed on HelloAsso, to review, already imported, blocked).
   The preview writes nothing. Online only: disabled with an explanation when the device is offline. */
import { inject, ref } from "vue";
import UiBadge from "../../components/ui/UiBadge.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import UiTile from "../../components/ui/UiTile.vue";
import { useNetworkUp } from "../../composables/network";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { formatEuros } from "../../lib/format";
import { createMembersApi } from "../../services/members";
import { BUCKETS, personLabel, rowsOf, type MembershipPreview } from "./helloassoImport";

const membersApi = createMembersApi(inject(CLIENT_KEY)!);
const online = useNetworkUp();

const preview = ref<MembershipPreview | null>(null);
const failure = ref("");
const busy = ref(false);

function reset(): void {
  preview.value = null;
  failure.value = "";
}

async function loadPreview(): Promise<void> {
  busy.value = true;
  failure.value = "";
  try {
    preview.value = await membersApi.helloAssoPreview();
  } catch (e) {
    preview.value = null;
    failure.value = errorText(e);
  } finally {
    busy.value = false;
  }
}

defineExpose({ reload: reset });
</script>

<template>
  <UiCard>
    <div class="mb-3.5 flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 flex-1 basis-80">
        <h2 class="mb-1 flex flex-wrap items-center gap-2 text-base font-bold">
          🔄 Synchroniser les adhésions HelloAsso
          <UiBadge color="blue" variant="soft">Campagne d'adhésion</UiBadge>
        </h2>
        <p class="text-[13px] text-slate-500">
          Lit la campagne d'adhésion HelloAsso réglée dans Paramètres et classe chaque inscription : nouvel adhérent, renouvellement,
          modification sur HelloAsso, cas à vérifier… L'aperçu n'enregistre rien et aucun e-mail n'est envoyé.
        </p>
      </div>
      <UiButton data-testid="ha-import-preview" :disabled="!online || busy" :busy="busy && 'Lecture de HelloAsso…'" @click="loadPreview">
        🔍 Prévisualiser l'import
      </UiButton>
    </div>

    <p
      v-if="!online"
      data-testid="ha-import-offline"
      class="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800"
    >
      📴 Appareil hors ligne : la synchronisation lit HelloAsso et écrit dans la base du club, elle n'est possible qu'avec une connexion.
    </p>

    <p
      v-if="failure"
      data-testid="ha-import-error"
      class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700"
    >
      ❌ {{ failure }}
    </p>

    <div v-if="preview" data-testid="ha-import-result" class="border-t border-slate-200 pt-4">
      <p data-testid="ha-import-campaign" class="mb-3 text-[13px] text-slate-600">
        Campagne
        <b class="font-mono">{{ preview.campaign }}</b>
        → saison
        <b>{{ preview.season }}</b>
      </p>
      <p
        v-if="preview.blocked_reason"
        data-testid="ha-import-blocked"
        class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] font-semibold text-red-700"
      >
        ⛔ {{ preview.blocked_reason }}
      </p>

      <div class="mb-4 grid grid-cols-2 gap-2.5 md:grid-cols-3 lg:grid-cols-6">
        <UiTile v-for="bucket in BUCKETS" :key="bucket.name" :label="bucket.label">
          <span :data-testid="`ha-count-${bucket.name}`" class="text-lg">{{ preview.counts[bucket.name] }}</span>
        </UiTile>
      </div>

      <template v-for="bucket in BUCKETS" :key="bucket.name">
        <section v-if="rowsOf(preview, bucket.name).length" :data-testid="`ha-section-${bucket.name}`" class="mb-4">
          <h3 class="mb-1.5 flex items-center gap-2 text-[13.5px] font-bold">
            {{ bucket.label }}
            <UiBadge :color="bucket.color">{{ rowsOf(preview, bucket.name).length }}</UiBadge>
          </h3>
          <div class="max-h-80 overflow-auto rounded-md border border-slate-200">
            <table class="w-full text-xs">
              <thead class="bg-slate-50 text-left">
                <tr>
                  <th class="px-2.5 py-1.5">Adhérent</th>
                  <th class="px-2.5 py-1.5">Naissance</th>
                  <th class="px-2.5 py-1.5">Tarif</th>
                  <th class="px-2.5 py-1.5">Montant</th>
                  <th class="px-2.5 py-1.5">Statut HelloAsso</th>
                  <th class="px-2.5 py-1.5">Motif</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in rowsOf(preview, bucket.name)"
                  :key="row.item_id"
                  :data-testid="`ha-row-${bucket.name}`"
                  class="border-t border-slate-100"
                >
                  <td class="px-2.5 py-1.5 font-semibold">{{ personLabel(row) }}</td>
                  <td class="px-2.5 py-1.5">{{ row.birth_date || "—" }}</td>
                  <td class="px-2.5 py-1.5">{{ row.tarif_name }}</td>
                  <td class="px-2.5 py-1.5">{{ formatEuros(row.amount) }}</td>
                  <td class="px-2.5 py-1.5">{{ row.status }}</td>
                  <td class="px-2.5 py-1.5 text-slate-500">{{ row.reason }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </div>
  </UiCard>
</template>
