<script setup lang="ts">
/* Import of the MyFFME licensee list (admin): the server matches the rows with the members, records their licence,
   passports, diplomas and health document, and marks their membership « Terminé ». Preview first (nothing written,
   rows left unmatched can be linked by hand), or import straight away with the automatic matches only. */
import { computed, inject, ref } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import UiTile from "../../components/ui/UiTile.vue";
import { CLIENT_KEY, errorText, unwrap, type Schemas } from "../../lib/client";
import { applyConfirmation, fileLabel, isXlsx, manualMatches, memberLabel, readBase64, sortedMembers } from "./ffme";

const emit = defineEmits<{ toast: [message: string, ms?: number] }>();
const client = inject(CLIENT_KEY)!;

const file = ref<{ name: string; label: string; content: string } | null>(null);
const preview = ref<Schemas["FfmePreview"] | null>(null);
const choices = ref<(number | null)[]>([]);
const done = ref<number | null>(null); // members updated by the last import
const busy = ref<"analyze" | "quick" | "apply" | null>(null);
const dragging = ref(false);
const input = ref<HTMLInputElement | null>(null);

const members = computed(() => sortedMembers(preview.value?.users ?? []));

function reset(): void {
  file.value = null;
  preview.value = null;
  choices.value = [];
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

async function analyze(): Promise<void> {
  if (!file.value) {
    return;
  }
  busy.value = "analyze";
  try {
    const body = { filename: file.value.name, content_base64: file.value.content };
    const data = await unwrap(client.POST("/api/ffme/preview", { body }));
    choices.value = data.unmatched.map(() => null);
    preview.value = data;
    emit("toast", "✅ Analyse terminée ! Vous pouvez vérifier les correspondances ci-dessous.");
  } catch (e) {
    emit("toast", `❌ Erreur analyse : ${errorText(e)}`, 8000);
  } finally {
    busy.value = null;
  }
}

async function send(manual: Schemas["FfmeManualMatch"][]): Promise<void> {
  const body = { filename: file.value!.name, content_base64: file.value!.content, manual_matches: manual };
  const data = await unwrap(client.POST("/api/ffme/import", { body }));
  emit("toast", `🎉 ${data.message}`);
  reset();
  done.value = data.updated_count;
}

async function quickImport(): Promise<void> {
  if (!file.value) {
    return;
  }
  if (
    !confirm(
      "Voulez-vous lancer l'importation directe ? Les licenciés reconnus automatiquement par N° de licence ou " +
        "Nom/Prénom seront mis à jour et basculés en statut « Terminé ».",
    )
  ) {
    return;
  }
  busy.value = "quick";
  try {
    await send([]);
  } catch (e) {
    emit("toast", `❌ Échec : ${errorText(e)}`, 8000);
  } finally {
    busy.value = null;
  }
}

async function apply(): Promise<void> {
  if (!file.value || !preview.value) {
    return;
  }
  const manual = manualMatches(preview.value.unmatched, choices.value);
  if (preview.value.matched_count + manual.length === 0) {
    emit("toast", "⚠️ Aucune modification à appliquer.");
    return;
  }
  if (!confirm(applyConfirmation(preview.value.matched_count, manual.length))) {
    return;
  }
  busy.value = "apply";
  try {
    await send(manual);
  } catch (e) {
    emit("toast", `❌ Échec : ${errorText(e)}`, 8000);
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
          📥 Importation de la liste des licenciés FFME (.xlsx)
          <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-800">Synchronisation Fédérale</span>
        </h2>
        <p class="text-[13px] text-slate-500">
          Téléversez le fichier Excel exporté depuis le portail <b>MyFFME</b>. Le système analyse la liste, réconcilie les licenciés avec la
          base du club (par N° de licence ou par Nom/Prénom), enregistre les licences, diplômes et documents de santé, et bascule les
          adhérents associés en statut <b>« Terminé »</b>.
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
        <b>« Terminé »</b>.
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
        <UiButton
          variant="muted"
          data-testid="ffme-quick-import"
          :disabled="!file || !!busy"
          :busy="busy === 'quick' && 'Importation en cours…'"
          @click="quickImport"
        >
          ⚡ Importer & Fusionner directement
        </UiButton>
      </div>

      <div v-if="preview" data-testid="ffme-preview" class="border-t border-slate-200 pt-4">
        <div class="mb-4 grid grid-cols-2 gap-2.5 md:grid-cols-4">
          <UiTile label="Lignes Excel traitées"
            ><span data-testid="ffme-rows" class="text-lg">{{ preview.stats.total_processed }}</span></UiTile
          >
          <UiTile label="🟢 Trouvés par N° licence"
            ><span data-testid="ffme-by-licence" class="text-lg text-green-600">{{ preview.stats.matched_by_licence }}</span></UiTile
          >
          <UiTile label="🔵 Trouvés par nom & prénom"
            ><span data-testid="ffme-by-name" class="text-lg text-blue-600">{{ preview.stats.matched_by_name }}</span></UiTile
          >
          <UiTile label="⚠️ Non trouvés dans la base"
            ><span data-testid="ffme-unmatched-count" class="text-lg text-red-600">{{ preview.unmatched.length }}</span></UiTile
          >
        </div>

        <div v-if="preview.unmatched.length" class="mb-4 rounded-lg border border-red-200 bg-red-50 px-3.5 py-3">
          <div class="mb-1.5 text-[13.5px] font-bold text-red-800">
            ⚠️ Licenciés FFME non reconnus automatiquement dans la base ({{ preview.unmatched.length }})
          </div>
          <p class="mb-2.5 text-xs text-red-900">
            Ces licenciés sont présents dans le fichier FFME mais n'ont pas pu être associés de façon certaine. Vous pouvez associer chaque
            ligne à un adhérent du club ou la laisser ignorée.
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
                <tr v-for="(row, i) in preview.unmatched" :key="i" data-testid="ffme-unmatched" class="border-t border-slate-100">
                  <td class="px-2.5 py-1.5 font-semibold">{{ row.nom }} {{ row.prenom }}</td>
                  <td class="px-2.5 py-1.5 font-mono">{{ row.licence || "—" }}</td>
                  <td class="px-2.5 py-1.5">{{ row.birth_date || "—" }}</td>
                  <td class="px-2.5 py-1.5">
                    <select
                      v-model="choices[i]"
                      data-testid="ffme-match"
                      :aria-label="`Adhérent associé à ${row.nom} ${row.prenom}`"
                      class="w-full min-w-48 rounded-md border border-slate-300 px-1.5 py-1 text-xs"
                    >
                      <option :value="null">-- Ignorer cette ligne --</option>
                      <option v-for="m in members" :key="m.id" :value="m.id">{{ memberLabel(m) }}</option>
                    </select>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-2.5">
          <UiButton data-testid="ffme-apply" :disabled="!!busy" :busy="busy === 'apply' && 'Enregistrement…'" @click="apply">
            ✅ Appliquer et enregistrer en base de données
          </UiButton>
          <span data-testid="ffme-matched" class="text-xs text-slate-500"
            >{{ preview.matched_count }} adhérents réconciliés automatiquement.</span
          >
        </div>
      </div>
    </template>
  </UiCard>
</template>
