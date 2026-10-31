<script setup lang="ts">
/* Synchronisation of the HelloAsso membership campaign (admin): the server reads the campaign picked in the select
   (the one chosen in Paramètres › Campagnes at first; another one applies to this sync only, nothing is saved) and sorts every registration into a bucket (new, renewal, changed on HelloAsso, to review, already
   imported, blocked), the latest registrations first.
   The preview writes nothing; the new, renewal and changed rows start checked, and the checked ones are imported once
   confirmed (the server reads HelloAsso again and refuses decisions that no longer match). The result lists the members
   written, linked to their record. Online only: disabled with an explanation when the device is offline. */
import { computed, inject, onMounted, ref } from "vue";
import UiBadge from "../../components/ui/UiBadge.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import UiTile from "../../components/ui/UiTile.vue";
import { useNetworkUp } from "../../composables/network";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { formatDayText, formatEuros } from "../../lib/format";
import { createIntegrationsApi } from "../../services/integrations";
import { createMembersApi } from "../../services/members";
import { dialogs } from "../../composables/dialogs";
import {
  BUCKETS,
  campaignOptions,
  changeLines,
  decisionsOf,
  initialChoices,
  isCheckable,
  lastSyncText,
  memberHref,
  needsIdentityChoice,
  personLabel,
  refundText,
  RESULT_GROUPS,
  resultSummary,
  reviewOptions,
  rowsOf,
  type Choices,
  type MembershipImportResult,
  type MembershipPreview,
} from "./helloassoImport";

const client = inject(CLIENT_KEY)!;
const membersApi = createMembersApi(client);
const integrationsApi = createIntegrationsApi(client);
const online = useNetworkUp();

const preview = ref<MembershipPreview | null>(null);
const choices = ref<Choices>({});
const done = ref<MembershipImportResult | null>(null);
const failure = ref("");
const busy = ref<"preview" | "import" | null>(null);
const lastSync = ref<string | null>(null); // null until known
// The membership forms of the select, empty until loaded (or when they can't be read: the server's active one is used)
const campaigns = ref<{ value: string; label: string }[]>([]);
const campaign = ref<string | null>(null); // null: the active one, chosen by the server

async function loadCampaigns(): Promise<void> {
  try {
    const membership = (await integrationsApi.helloAssoCampaigns()).membership;
    campaigns.value = campaignOptions(membership);
    campaign.value = membership.active?.slug ?? campaigns.value[0]?.value ?? null;
  } catch (e) {
    console.warn("Campagnes HelloAsso :", e);
  }
}

/** Another campaign: the preview shown no longer matches it. */
function pickCampaign(slug: string): void {
  campaign.value = slug;
  reset();
}

async function loadLastSync(): Promise<void> {
  try {
    lastSync.value = lastSyncText((await membersApi.helloAssoLastSync()).last_sync);
  } catch (e) {
    console.warn("Dernière synchronisation HelloAsso :", e);
  }
}

onMounted(() => {
  if (online.value) {
    void loadLastSync();
    void loadCampaigns();
  }
});

/** Rows that will be written: the checked ones (rows to review: a choice other than skip). */
const selectedCount = computed(() => Object.values(choices.value).filter((choice) => choice !== "skip").length);

function reset(): void {
  preview.value = null;
  choices.value = {};
  done.value = null;
  failure.value = "";
}

async function loadPreview(): Promise<void> {
  busy.value = "preview";
  reset();
  try {
    preview.value = await membersApi.helloAssoPreview(campaign.value);
    choices.value = initialChoices(preview.value);
  } catch (e) {
    failure.value = errorText(e);
  } finally {
    busy.value = null;
  }
}

function choose(itemId: number, choice: string): void {
  choices.value = { ...choices.value, [itemId]: choice };
}

async function apply(): Promise<void> {
  const shown = preview.value;
  const previewedCampaign = campaign.value;
  if (!shown || !selectedCount.value) {
    return;
  }
  const confirmed = await dialogs.confirm({
    title: "Importer les adhésions HelloAsso",
    message: `Enregistrer ${selectedCount.value} inscription(s) HelloAsso dans la base des adhérents (saison ${shown.season}) ? Aucun e-mail n'est envoyé.`,
    confirmLabel: "Importer",
  });
  if (!confirmed) {
    return;
  }
  busy.value = "import";
  failure.value = "";
  try {
    const result = await membersApi.helloAssoImport({
      season: shown.season,
      campaign: previewedCampaign,
      decisions: decisionsOf(shown, choices.value),
    });
    reset();
    done.value = result;
    void loadLastSync();
  } catch (e) {
    failure.value = errorText(e);
  } finally {
    busy.value = null;
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
          Lit la campagne d'adhésion HelloAsso choisie ci-dessous (par défaut la campagne active de Paramètres › Campagnes ; un autre choix
          ne vaut que pour cette synchronisation) et classe chaque inscription : nouvel adhérent, renouvellement, modification sur
          HelloAsso, cas à vérifier… L'aperçu n'enregistre rien et aucun e-mail n'est envoyé.
        </p>
        <label v-if="campaigns.length" class="mt-2 flex flex-wrap items-center gap-2 text-[12.5px] font-semibold text-slate-500">
          Campagne
          <select
            data-testid="ha-import-campaign-select"
            :value="campaign"
            :disabled="!!busy"
            class="min-w-0 max-w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-[12.5px] text-slate-800"
            @change="pickCampaign(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="option in campaigns" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
        <p v-if="lastSync" data-testid="ha-last-sync" class="mt-1 text-xs font-semibold text-slate-600">🕒 {{ lastSync }}</p>
      </div>
      <UiButton
        data-testid="ha-import-preview"
        :disabled="!online || !!busy"
        :busy="busy === 'preview' && 'Lecture de HelloAsso…'"
        @click="loadPreview"
      >
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

    <div v-if="done" data-testid="ha-import-done" class="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
      <div class="mb-2 text-[15px] font-bold text-emerald-800">{{ resultSummary(done) }}</div>
      <ul class="flex flex-col gap-1 text-[13px]">
        <template v-for="group in RESULT_GROUPS" :key="group.key">
          <li v-for="member in done[group.key]" :key="member.item_id" :data-testid="group.testId">
            {{ group.icon }}
            <a :href="memberHref(member, done.season)" class="font-semibold text-blue-700 underline">{{ personLabel(member) }}</a>
            <span class="text-slate-500">— {{ member.tarif_name }}</span>
          </li>
        </template>
      </ul>
    </div>

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
                  <th class="w-8 px-2.5 py-1.5"><span class="sr-only">Importer</span></th>
                  <th class="px-2.5 py-1.5">Adhérent</th>
                  <th class="px-2.5 py-1.5">Inscrit le</th>
                  <th class="px-2.5 py-1.5">Payé le</th>
                  <th class="px-2.5 py-1.5">Naissance</th>
                  <th class="px-2.5 py-1.5">Licence</th>
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
                  <td class="px-2.5 py-1.5">
                    <input
                      v-if="isCheckable(row)"
                      type="checkbox"
                      data-testid="ha-check"
                      :checked="choices[row.item_id] === 'import'"
                      :aria-label="`Importer ${personLabel(row)}`"
                      @change="choose(row.item_id, ($event.target as HTMLInputElement).checked ? 'import' : 'skip')"
                    />
                  </td>
                  <td class="px-2.5 py-1.5 font-semibold">{{ personLabel(row) }}</td>
                  <td class="px-2.5 py-1.5" data-testid="ha-order-date">{{ formatDayText(row.order_date) || "—" }}</td>
                  <td class="px-2.5 py-1.5" data-testid="ha-payment-date">{{ formatDayText(row.payment_date) || "—" }}</td>
                  <td class="px-2.5 py-1.5" data-testid="ha-birth-date">{{ formatDayText(row.birth_date) || "—" }}</td>
                  <td class="px-2.5 py-1.5 font-mono" data-testid="ha-licence">{{ row.licence || "—" }}</td>
                  <td class="px-2.5 py-1.5">{{ row.tarif_name }}</td>
                  <td class="px-2.5 py-1.5">{{ formatEuros(row.amount) }}</td>
                  <td class="px-2.5 py-1.5">
                    {{ row.status }}
                    <span v-if="row.refund_date" data-testid="ha-refund-date" class="block text-slate-500">{{ refundText(row) }}</span>
                  </td>
                  <td class="px-2.5 py-1.5 text-slate-500">
                    {{ row.reason }}
                    <span v-for="line in changeLines(row)" :key="line" class="block font-semibold text-slate-700">{{ line }}</span>
                    <select
                      v-if="needsIdentityChoice(row)"
                      data-testid="ha-review-choice"
                      :value="choices[row.item_id]"
                      :aria-label="`Choix pour ${personLabel(row)}`"
                      class="mt-1 block w-full min-w-56 rounded-md border border-slate-300 px-1.5 py-1 text-xs text-slate-800"
                      @change="choose(row.item_id, ($event.target as HTMLSelectElement).value)"
                    >
                      <option v-for="option in reviewOptions(row)" :key="option.value" :value="option.value">{{ option.label }}</option>
                    </select>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>

      <div v-if="!preview.blocked_reason" class="flex flex-wrap items-center justify-between gap-2.5 border-t border-slate-200 pt-3">
        <UiButton
          data-testid="ha-import-apply"
          :disabled="!online || !!busy || !selectedCount"
          :busy="busy === 'import' && 'Import en cours…'"
          @click="apply"
        >
          ✅ Importer la sélection
        </UiButton>
        <span data-testid="ha-import-selected" class="text-xs text-slate-500">{{ selectedCount }} inscription(s) sélectionnée(s)</span>
      </div>
    </div>
  </UiCard>
</template>
