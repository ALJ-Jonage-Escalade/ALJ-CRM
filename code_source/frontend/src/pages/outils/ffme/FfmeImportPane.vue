<script setup lang="ts">
/* Import of the MyFFME licensee list (admin): the server matches the rows with the members, records their licence,
   passports, diplomas and health document, and marks their membership « Terminé ». The preview lists every change
   (nothing written): rows left unmatched can be linked by hand (each pick is previewed again), rows can be left out,
   and a member matched by several rows blocks the import until only one is kept. */
import { computed, inject, ref } from "vue";
import UiBadge from "../../../components/ui/UiBadge.vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiCard from "../../../components/ui/UiCard.vue";
import UiTile from "../../../components/ui/UiTile.vue";
import { CLIENT_KEY, errorText, type Schemas } from "../../../lib/client";
import { createFfmeApi } from "../../../services/ffme";
import FfmeChangesTable from "./FfmeChangesTable.vue";
import {
  applyConfirmation,
  blockedUserIds,
  changeMatches,
  fileLabel,
  isXlsx,
  licenseeMatches,
  manualMatches,
  memberLabel,
  readBase64,
  sortChanges,
  sortedMembers,
} from "./ffme";
import { dialogs } from "../../../composables/dialogs";

const emit = defineEmits<{ toast: [message: string, ms?: number] }>();
const ffmeApi = createFfmeApi(inject(CLIENT_KEY)!);

const file = ref<{ name: string; label: string; content: string } | null>(null);
// The first analysis keeps the unmatched rows (and their pickers); `preview` follows the manual picks
const firstPreview = ref<Schemas["FfmePreview"] | null>(null);
const preview = ref<Schemas["FfmePreview"] | null>(null);
const choices = ref<(number | null)[]>([]);
const excludedRows = ref(new Set<number>());
const search = ref("");
const done = ref<number | null>(null); // members updated by the last import
const busy = ref<"analyze" | "refresh" | "apply" | null>(null);
let refreshId = 0; // only the answer to the last pick is shown
const dragging = ref(false);
const input = ref<HTMLInputElement | null>(null);

const members = computed(() => sortedMembers(firstPreview.value?.users ?? []));
const unmatched = computed(() => firstPreview.value?.unmatched ?? []);
const changes = computed(() => sortChanges(preview.value?.changes ?? []));
const shownChanges = computed(() => changes.value.filter((row) => changeMatches(row, search.value)));
const blocked = computed(() => blockedUserIds(changes.value, excludedRows.value));
const toApply = computed(() => changes.value.filter((row) => row.changes.length > 0 && !excludedRows.value.has(row.row_number)));
const withoutRegistrationCount = computed(() => changes.value.filter((row) => row.no_active_registration).length);
const stillUnmatchedCount = computed(() => choices.value.filter((choice) => choice == null).length);

function reset(): void {
  file.value = null;
  firstPreview.value = null;
  preview.value = null;
  choices.value = [];
  excludedRows.value = new Set();
  search.value = "";
  done.value = null;
  if (input.value) {
    input.value.value = "";
  }
}

async function pick(picked: File | undefined): Promise<void> {
  if (!picked) {
    return;
  }
  if (!isXlsx(picked.name)) {
    emit("toast", "⚠️ Seuls les fichiers Excel .xlsx sont acceptés.");
    return;
  }
  reset();
  file.value = { name: picked.name, label: fileLabel(picked), content: await readBase64(picked) };
}

function drop(event: DragEvent): void {
  dragging.value = false;
  void pick(event.dataTransfer?.files[0]);
}

function requestBody(): Schemas["FfmePreviewRequest"] {
  return { filename: file.value!.name, content_base64: file.value!.content, manual_matches: manualMatches(unmatched.value, choices.value) };
}

async function analyze(): Promise<void> {
  if (!file.value) {
    return;
  }
  busy.value = "analyze";
  try {
    const data = await ffmeApi.preview({ filename: file.value.name, content_base64: file.value.content, manual_matches: [] });
    choices.value = data.unmatched.map(() => null);
    excludedRows.value = new Set();
    firstPreview.value = data;
    preview.value = data;
    emit("toast", "✅ Analyse terminée ! Vous pouvez vérifier les modifications ci-dessous.");
  } catch (e) {
    emit("toast", `❌ Erreur analyse : ${errorText(e)}`, 8000);
  } finally {
    busy.value = null;
  }
}

/** A member picked (or « Ignorer ») for an unmatched row: the changes are previewed again with the manual matches. */
async function refresh(): Promise<void> {
  const id = ++refreshId;
  busy.value = "refresh";
  try {
    const data = await ffmeApi.preview(requestBody());
    if (id === refreshId) {
      preview.value = data;
    }
  } catch (e) {
    emit("toast", `❌ Erreur analyse : ${errorText(e)}`, 8000);
  } finally {
    if (id === refreshId) {
      busy.value = null;
    }
  }
}

function toggle(rowNumber: number): void {
  const excluded = new Set(excludedRows.value);
  if (!excluded.delete(rowNumber)) {
    excluded.add(rowNumber);
  }
  excludedRows.value = excluded;
}

async function apply(): Promise<void> {
  if (!file.value || !preview.value) {
    return;
  }
  if (toApply.value.length === 0) {
    emit("toast", "⚠️ Aucune modification à appliquer.");
    return;
  }
  if (
    !(await dialogs.confirm({
      title: "Appliquer les modifications",
      message: applyConfirmation(toApply.value),
      confirmLabel: "Appliquer",
    }))
  ) {
    return;
  }
  busy.value = "apply";
  try {
    const data = await ffmeApi.import({ ...requestBody(), excluded_rows: [...excludedRows.value].sort((a, b) => a - b) });
    emit("toast", `🎉 ${data.message}`);
    reset();
    done.value = data.updated_count;
  } catch (e) {
    emit("toast", `❌ Échec : ${errorText(e)}`, 8000);
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <UiCard>
    <div class="mb-3.5 flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 flex-1 basis-80">
        <h2 class="mb-1 flex flex-wrap items-center gap-2 text-base font-bold">
          📥 Importation de la liste des licenciés FFME (.xlsx)
          <UiBadge color="green" variant="soft">Synchronisation Fédérale</UiBadge>
        </h2>
        <p class="text-[13px] text-slate-500">
          Téléversez le fichier Excel exporté depuis le portail
          <b>MyFFME</b>
          . Le système analyse la liste, réconcilie les licenciés avec la base du club (par N° de licence ou par Nom/Prénom, vérifiés par la
          date de naissance) et liste toutes les modifications avant de les enregistrer : licences, passeports, diplômes, documents de
          santé, et passage des adhérents associés en statut
          <b>« Terminé »</b>
          .
        </p>
      </div>
      <a
        href="https://myffme.fr"
        target="_blank"
        rel="noopener"
        class="rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-300"
      >
        🌐 Portail MyFFME
      </a>
    </div>

    <div v-if="done !== null" data-testid="ffme-import-done" class="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-center">
      <div class="mb-1 text-2xl">🎉</div>
      <div class="mb-1 text-[15px] font-bold text-emerald-800">Importation FFME enregistrée avec succès !</div>
      <p class="mb-3 text-[13px] text-emerald-700">
        {{ done }} adhérents ont été mis à jour avec leurs licences, diplômes et documents de santé. Leurs statuts sont désormais passés en
        <b>« Terminé »</b>
        .
      </p>
      <UiButton variant="muted" small data-testid="ffme-import-again" @click="reset">🔄 Importer un autre fichier</UiButton>
    </div>

    <template v-else>
      <div
        data-testid="ffme-drop-zone"
        :class="[
          'mb-4 cursor-pointer rounded-xl border-2 border-dashed px-5 py-6 text-center transition-colors',
          dragging ? 'border-blue-500 bg-blue-50' : 'border-slate-300 bg-slate-50',
        ]"
        @click="input?.click()"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="drop"
      >
        <div class="mb-2 text-3xl">📊</div>
        <div class="mb-1 text-sm font-bold">Glissez-déposez le fichier Excel exporté depuis la FFME ici</div>
        <div class="mb-3 text-xs text-slate-500">ou cliquez pour parcourir vos fichiers (.xlsx)</div>
        <input
          ref="input"
          type="file"
          data-testid="ffme-file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          class="hidden"
          @change="pick(($event.target as HTMLInputElement).files?.[0])"
        />
        <UiButton variant="muted" small @click.stop="input?.click()">📁 Parcourir un fichier…</UiButton>
        <div v-if="file" data-testid="ffme-file-name" class="mt-2.5 text-[13px] font-semibold text-blue-600">{{ file.label }}</div>
      </div>

      <div class="mb-4 flex flex-wrap items-center gap-2.5">
        <UiButton data-testid="ffme-analyze" :disabled="!file || !!busy" :busy="busy === 'analyze' && 'Analyse en cours…'" @click="analyze">
          🔍 Analyser & Prévisualiser le fichier
        </UiButton>
      </div>

      <div v-if="preview" data-testid="ffme-preview" class="border-t border-slate-200 pt-4">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2.5">
          <h3 class="text-sm font-bold">Modifications prévues · Saison {{ preview.season }}</h3>
          <input
            v-model="search"
            type="search"
            data-testid="ffme-search"
            placeholder="Nom ou N° de licence…"
            aria-label="Rechercher un licencié par nom ou N° de licence"
            class="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
          />
        </div>
        <div class="mb-4 grid grid-cols-2 gap-2.5 md:grid-cols-5">
          <UiTile label="Lignes Excel traitées">
            <span data-testid="ffme-rows" class="text-lg">{{ preview.stats.total_processed }}</span>
          </UiTile>
          <UiTile label="✏️ Adhérents à modifier">
            <span data-testid="ffme-to-change" class="text-lg text-blue-600">{{ toApply.length }}</span>
          </UiTile>
          <UiTile label="🟢 Reconnus sans changement">
            <span data-testid="ffme-unchanged" class="text-lg text-green-600">{{ preview.unchanged_count }}</span>
          </UiTile>
          <UiTile label="⚠️ Sans inscription active">
            <span data-testid="ffme-no-registration" class="text-lg text-amber-600">{{ withoutRegistrationCount }}</span>
          </UiTile>
          <UiTile label="❓ Non trouvés dans la base">
            <span data-testid="ffme-unmatched-count" class="text-lg text-red-600">{{ stillUnmatchedCount }}</span>
          </UiTile>
        </div>

        <div v-if="unmatched.length" class="mb-4 rounded-lg border border-red-200 bg-red-50 px-3.5 py-3">
          <div class="mb-1.5 text-[13.5px] font-bold text-red-800">
            ⚠️ Licenciés FFME non reconnus automatiquement dans la base ({{ unmatched.length }})
          </div>
          <p class="mb-2.5 text-xs text-red-900">
            Ces licenciés sont présents dans le fichier FFME mais n'ont pas pu être associés de façon certaine. Vous pouvez associer chaque
            ligne à un adhérent du club (ses modifications s'ajoutent au tableau ci-dessous) ou la laisser ignorée.
          </p>
          <div class="max-h-72 overflow-auto rounded-md border border-red-200 bg-white">
            <table class="w-full text-xs">
              <thead class="bg-slate-50 text-left">
                <tr>
                  <th class="px-2.5 py-1.5">Licencié FFME (Fichier)</th>
                  <th class="px-2.5 py-1.5">N° Licence</th>
                  <th class="px-2.5 py-1.5">Naissance</th>
                  <th class="px-2.5 py-1.5">Associer à un adhérent du club</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="(row, i) in unmatched" :key="row.row_number">
                  <tr v-if="licenseeMatches(row, search)" data-testid="ffme-unmatched" class="border-t border-slate-100">
                    <td class="px-2.5 py-1.5 font-semibold">{{ row.nom }} {{ row.prenom }}</td>
                    <td class="px-2.5 py-1.5 font-mono">{{ row.licence || "—" }}</td>
                    <td class="px-2.5 py-1.5">{{ row.birth_date || "—" }}</td>
                    <td class="px-2.5 py-1.5">
                      <select
                        v-model="choices[i]"
                        data-testid="ffme-match"
                        :aria-label="`Adhérent associé à ${row.nom} ${row.prenom}`"
                        class="w-full min-w-48 rounded-md border border-slate-300 px-1.5 py-1 text-xs"
                        @change="refresh"
                      >
                        <option :value="null">-- Ignorer cette ligne --</option>
                        <option v-for="m in members" :key="m.id" :value="m.id">{{ memberLabel(m) }}</option>
                      </select>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>

        <FfmeChangesTable
          v-if="shownChanges.length"
          class="mb-4"
          :rows="shownChanges"
          :excluded-rows="excludedRows"
          :blocked-user-ids="blocked"
          @toggle="toggle"
        />
        <p v-else class="mb-4 text-xs text-slate-500">Aucune modification à afficher.</p>

        <div class="flex flex-wrap items-center justify-between gap-2.5">
          <UiButton
            data-testid="ffme-apply"
            :disabled="!!busy || blocked.size > 0"
            :busy="busy === 'apply' && 'Enregistrement…'"
            @click="apply"
          >
            ✅ Appliquer et enregistrer en base de données
          </UiButton>
          <span v-if="blocked.size" data-testid="ffme-blocked" class="text-xs font-semibold text-red-700">
            Un adhérent est rapproché par plusieurs lignes : décochez-en une pour pouvoir appliquer.
          </span>
        </div>
      </div>
    </template>
  </UiCard>
</template>
