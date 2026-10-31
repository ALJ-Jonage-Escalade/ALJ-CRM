<script setup lang="ts">
/* Synchronisation of the HelloAsso membership campaign (admin): the server reads the campaign set in Paramètres and
   sorts every registration into a bucket (new, renewal, changed on HelloAsso, to review, already imported, blocked).
   The preview writes nothing; the new, renewal and changed rows start checked, and the checked ones are imported once
   confirmed (the server reads HelloAsso again and refuses decisions that no longer match). The result lists the members
   written, linked to their record. Online only: disabled with an explanation when the device is offline. */
import { computed, inject, ref } from "vue";
import UiBadge from "../../components/ui/UiBadge.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import UiTile from "../../components/ui/UiTile.vue";
import { useNetworkUp } from "../../composables/network";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { formatEuros } from "../../lib/format";
import { createMembersApi } from "../../services/members";
import { dialogs } from "../../composables/dialogs";
import {
  BUCKETS,
  decisionsOf,
  initialChoices,
  isCheckable,
  memberHref,
  personLabel,
  rowsOf,
  type Choices,
  type MembershipImportResult,
  type MembershipPreview,
} from "./helloassoImport";

const membersApi = createMembersApi(inject(CLIENT_KEY)!);
const online = useNetworkUp();

const preview = ref<MembershipPreview | null>(null);
const choices = ref<Choices>({});
const done = ref<MembershipImportResult | null>(null);
const failure = ref("");
const busy = ref<"preview" | "import" | null>(null);

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
    preview.value = await membersApi.helloAssoPreview();
    choices.value = initialChoices(preview.value);
  } catch (e) {
    failure.value = errorText(e);
  } finally {
    busy.value = null;
  }
}

function toggle(itemId: number, checked: boolean): void {
  choices.value = { ...choices.value, [itemId]: checked ? "import" : "skip" };
}

async function apply(): Promise<void> {
  const shown = preview.value;
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
    const result = await membersApi.helloAssoImport({ season: shown.season, decisions: decisionsOf(shown, choices.value) });
    reset();
    done.value = result;
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
          Lit la campagne d'adhésion HelloAsso réglée dans Paramètres et classe chaque inscription : nouvel adhérent, renouvellement,
          modification sur HelloAsso, cas à vérifier… L'aperçu n'enregistre rien et aucun e-mail n'est envoyé.
        </p>
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
      <div class="mb-2 text-[15px] font-bold text-emerald-800">
        🎉 Import terminé (saison {{ done.season }}) : {{ done.counts.created }} adhérent{{ done.counts.created > 1 ? "s" : "" }} créé{{
          done.counts.created > 1 ? "s" : ""
        }}, {{ done.counts.skipped }} inscription(s) non importée(s).
      </div>
      <ul v-if="done.created.length" class="flex flex-col gap-1 text-[13px]">
        <li v-for="member in done.created" :key="member.item_id" data-testid="ha-created">
          🆕
          <a :href="memberHref(member, done.season)" class="font-semibold text-blue-700 underline">{{ personLabel(member) }}</a>
          <span class="text-slate-500">— {{ member.tarif_name }}</span>
        </li>
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
                  <td class="px-2.5 py-1.5">
                    <input
                      v-if="isCheckable(row)"
                      type="checkbox"
                      data-testid="ha-check"
                      :checked="choices[row.item_id] === 'import'"
                      :aria-label="`Importer ${personLabel(row)}`"
                      @change="toggle(row.item_id, ($event.target as HTMLInputElement).checked)"
                    />
                  </td>
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
