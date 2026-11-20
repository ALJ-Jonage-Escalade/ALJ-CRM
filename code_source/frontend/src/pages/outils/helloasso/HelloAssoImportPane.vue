<script setup lang="ts">
/* Synchronisation of the HelloAsso membership campaign (admin): the server reads the campaign picked in the select
   (the one chosen in Paramètres › Campagnes at first; another one applies to this sync only, nothing is saved) and sorts every registration into a bucket (new, renewal, changed on HelloAsso, to review, already
   imported, blocked), the latest registrations first.
   The preview writes nothing; the new, renewal and changed rows start checked, a row to review is checked once its
   choice is made, and the checked ones are imported once confirmed. A registration made under another person's name
   (a parent for their child) is attached by hand to a member, with a comment (the server reads HelloAsso again and refuses decisions that no longer match). The result lists the members
   written, linked to their record. Online only: disabled with an explanation when the device is offline. */
import { computed, inject, nextTick, onMounted, ref } from "vue";
import UiBadge from "../../../components/ui/UiBadge.vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiCard from "../../../components/ui/UiCard.vue";
import UiTile from "../../../components/ui/UiTile.vue";
import AttachPicker from "./AttachPicker.vue";
import CorrectionDialog from "./CorrectionDialog.vue";
import CorrectionRequestDialog from "./CorrectionRequestDialog.vue";
import { useNetworkUp } from "../../../composables/network";
import { CLIENT_KEY, errorText } from "../../../lib/client";
import { formatDayText, formatEuros } from "../../../lib/format";
import { createIntegrationsApi } from "../../../services/integrations";
import { createMembersApi } from "../../../services/members";
import { dialogs } from "../../../composables/dialogs";
import {
  ATTACH,
  attachedMemberId,
  attachLines,
  BUCKETS,
  campaignOptions,
  canAttach,
  canCorrect,
  canRequest,
  changeLines,
  decisionsOf,
  describeMove,
  FOLDED_BUCKETS,
  incompleteRows,
  initialChoices,
  isCheckable,
  keepChoices,
  correctionLines,
  lastSyncText,
  memberHref,
  needsIdentityChoice,
  personLabel,
  refundText,
  RESULT_GROUPS,
  resultSummary,
  reviewOptions,
  rowProblem,
  rowsOf,
  searchRows,
  selectedRows,
  statusIcon,
  type BucketName,
  type Choices,
  type MembershipImportResult,
  type MembershipPreview,
  type RowMove,
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
// The search of each table (a filter of the view only: the checked rows it hides are still imported)
const searches = ref<Partial<Record<BucketName, string>>>({});

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

/** The sections of the preview: the non-empty buckets, with their rows and the ones matching their search. */
const sections = computed(() => {
  const shown = preview.value;
  if (!shown) {
    return [];
  }
  return BUCKETS.map((bucket) => {
    const rows = rowsOf(shown, bucket.name);
    return { ...bucket, rows, matching: searchRows(rows, searches.value[bucket.name] ?? "") };
  }).filter((section) => section.rows.length);
});

/** Rows that will be written: the checked ones with nothing missing. */
const selectedCount = computed(() => (preview.value ? selectedRows(preview.value, choices.value).length : 0));
/** Checked rows still missing something (an attach without member or comment): the import waits for them. */
const incompleteCount = computed(() => (preview.value ? incompleteRows(preview.value, choices.value).length : 0));

// The registration whose data the admin is correcting (its HelloAsso item id), null when the dialog is closed
const fixingId = ref<number | null>(null);
const fixingRow = computed(() => preview.value?.rows.find((row) => row.item_id === fixingId.value) ?? null);
// The last correction moved the row to another section: announced in the dialog, the row shown once it closes
const move = ref<RowMove | null>(null);
const fixingOpen = computed({
  get: () => fixingRow.value !== null,
  set: (isOpen: boolean) => {
    if (!isOpen) {
      void closeFixing();
    }
  },
});
// Sections unfolded to show a moved row (the others keep their default), and that row, highlighted
const unfolded = ref<BucketName[]>([]);
const highlighted = ref<number | null>(null);

// The correction request dialog: the rows that can be asked, and those checked on opening (null: closed)
const requestable = computed(() => preview.value?.rows.filter(canRequest) ?? []);
const requestPicked = ref<number[] | null>(null);
const requestOpen = computed({
  get: () => requestPicked.value !== null,
  set: (isOpen: boolean) => {
    if (!isOpen) {
      requestPicked.value = null;
    }
  },
});

/** The preview recomputed after a correction: the move it caused, if any; the admin's choices kept on the rows that
    did not move. */
function corrected(updated: MembershipPreview): void {
  const before = preview.value;
  if (before && fixingId.value !== null) {
    move.value = describeMove(before, updated, fixingId.value, choices.value);
    choices.value = keepChoices(before, updated, choices.value);
  }
  preview.value = updated;
}

async function closeFixing(): Promise<void> {
  const itemId = fixingId.value;
  const moved = move.value;
  fixingId.value = null;
  move.value = null;
  if (moved && itemId !== null) {
    await showRow(itemId);
  }
}

/** Unfolds the row's section (its search cleared), then scrolls to the row and highlights it. */
async function showRow(itemId: number): Promise<void> {
  const row = preview.value?.rows.find((found) => found.item_id === itemId);
  if (!row) {
    return;
  }
  unfolded.value = [...unfolded.value, row.bucket];
  searches.value = { ...searches.value, [row.bucket]: "" };
  highlighted.value = itemId;
  await nextTick();
  document.querySelector(`[data-item-id="${itemId}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
}

function reset(): void {
  preview.value = null;
  choices.value = {};
  searches.value = {};
  unfolded.value = [];
  highlighted.value = null;
  requestPicked.value = null;
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

/** The row's choice: picking one checks the row. */
function choose(itemId: number, choice: string): void {
  const current = choices.value[itemId];
  choices.value = { ...choices.value, [itemId]: { checked: true, choice, comment: current?.comment ?? "" } };
}

/** Checked or unchecked: the choice is kept. */
function check(itemId: number, checked: boolean): void {
  const current = choices.value[itemId];
  if (current) {
    choices.value = { ...choices.value, [itemId]: { ...current, checked } };
  }
}

/** The member picked for an attach (null: picking another one). */
function pickMember(itemId: number, memberId: number | null): void {
  choose(itemId, `${ATTACH}${memberId ?? ""}`);
}

function setComment(itemId: number, text: string): void {
  const current = choices.value[itemId];
  if (current) {
    choices.value = { ...choices.value, [itemId]: { ...current, comment: text } };
  }
}

/** The value of a row's select: an attach shows as its option, whichever member is picked. */
function selectValue(choice: string): string {
  return choice.startsWith(ATTACH) ? ATTACH : choice;
}

async function apply(): Promise<void> {
  const shown = preview.value;
  const previewedCampaign = campaign.value;
  if (!shown || !selectedCount.value || incompleteCount.value) {
    return;
  }
  const attachments = attachLines(shown, choices.value);
  const confirmed = await dialogs.confirm({
    title: "Importer les adhésions HelloAsso",
    message:
      `Enregistrer ${selectedCount.value} inscription(s) HelloAsso dans la base des adhérents (saison ${shown.season}) ? Aucun e-mail n'est envoyé.` +
      (attachments.length ? `\n\nRattachements :\n${attachments.join("\n")}` : ""),
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

      <div v-if="requestable.length" class="mb-4">
        <UiButton variant="muted" small data-testid="ha-request-all" @click="requestPicked = requestable.map((row) => row.item_id)">
          📧 Demander des corrections aux familles ({{ requestable.length }} inscription(s) à corriger)
        </UiButton>
      </div>

      <!-- Folded or unfolded by the admin; the sections with nothing to do start folded -->
      <details
        v-for="section in sections"
        :key="section.name"
        :data-testid="`ha-section-${section.name}`"
        :open="!FOLDED_BUCKETS.includes(section.name) || unfolded.includes(section.name)"
        class="group mb-4"
      >
        <summary class="mb-1.5 flex cursor-pointer list-none items-center [&::-webkit-details-marker]:hidden gap-2 text-[13.5px] font-bold">
          <span aria-hidden="true" class="text-slate-400 transition-transform group-open:rotate-90">▶</span>
          {{ section.label }}
          <UiBadge :color="section.color">{{ section.rows.length }}</UiBadge>
        </summary>
        <input
          v-model="searches[section.name]"
          type="search"
          data-testid="ha-search"
          :aria-label="`Rechercher dans ${section.label}`"
          placeholder="🔍 Rechercher (nom, prénom, licence, tarif, naissance, motif)…"
          class="mb-1.5 w-full max-w-md rounded-lg border border-slate-300 px-2.5 py-1 text-[12.5px]"
        />
        <div class="max-h-80 overflow-auto rounded-md border border-slate-200">
          <!-- Same fixed widths in every section (table-fixed): the columns line up from one table to the next.
                 Tarif takes the remaining width; below the minimum width, the table scrolls -->
          <table class="w-full min-w-[1180px] table-fixed text-xs">
            <colgroup>
              <col class="w-8" />
              <col class="w-[170px]" />
              <col class="w-[84px]" />
              <col class="w-[84px]" />
              <col class="w-[84px]" />
              <col class="w-[76px]" />
              <col />
              <col class="w-[72px]" />
              <col class="w-[72px]" />
              <col class="w-[350px]" />
            </colgroup>
            <thead class="bg-slate-50 text-left">
              <tr>
                <th class="px-2.5 py-1.5"><span class="sr-only">Importer</span></th>
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
              <tr v-if="!section.matching.length" data-testid="ha-search-empty">
                <td colspan="10" class="px-2.5 py-3 text-center text-slate-500">Aucune inscription ne correspond à la recherche.</td>
              </tr>
              <tr
                v-for="row in section.matching"
                :key="row.item_id"
                :data-testid="`ha-row-${section.name}`"
                :data-item-id="row.item_id"
                :data-highlighted="highlighted === row.item_id || undefined"
                :class="['border-t border-slate-100 transition-colors', highlighted === row.item_id && 'bg-yellow-100']"
              >
                <td class="px-2.5 py-1.5">
                  <input
                    v-if="isCheckable(row)"
                    type="checkbox"
                    data-testid="ha-check"
                    :checked="choices[row.item_id]?.checked"
                    :disabled="!choices[row.item_id]?.choice"
                    :title="choices[row.item_id]?.choice ? undefined : 'Choisissez d\'abord quoi faire'"
                    :aria-label="`Importer ${personLabel(row)}`"
                    @change="check(row.item_id, ($event.target as HTMLInputElement).checked)"
                  />
                </td>
                <td data-testid="ha-person" class="px-2.5 py-1.5 font-semibold break-words">
                  {{ personLabel(row) }}
                  <UiBadge v-if="row.corrections.length" color="blue" variant="soft" data-testid="ha-corrected">corrigée</UiBadge>
                  <template v-if="row.attached_to">
                    →
                    <a :href="memberHref(row.attached_to, preview.season)" class="text-blue-700 underline">
                      {{ personLabel(row.attached_to) }}
                    </a>
                  </template>
                </td>
                <td class="px-2.5 py-1.5" data-testid="ha-order-date">{{ formatDayText(row.order_date) || "—" }}</td>
                <td class="px-2.5 py-1.5" data-testid="ha-payment-date">{{ formatDayText(row.payment_date) || "—" }}</td>
                <td class="px-2.5 py-1.5" data-testid="ha-birth-date">{{ formatDayText(row.birth_date) || "—" }}</td>
                <td class="px-2.5 py-1.5" data-testid="ha-licence">{{ row.licence || "—" }}</td>
                <td class="px-2.5 py-1.5 break-words">{{ row.tarif_name }}</td>
                <td class="px-2.5 py-1.5">{{ formatEuros(row.amount) }}</td>
                <td class="px-2.5 py-1.5">
                  <span
                    role="img"
                    data-testid="ha-status"
                    class="cursor-help"
                    :title="statusIcon(row.status).tooltip"
                    :aria-label="statusIcon(row.status).tooltip"
                  >
                    {{ statusIcon(row.status).icon }}
                  </span>
                  <span v-if="row.refund_date" data-testid="ha-refund-date" class="block text-slate-500">{{ refundText(row) }}</span>
                </td>
                <td class="px-2.5 py-1.5 break-words text-slate-500">
                  {{ row.reason }}
                  <span v-for="line in changeLines(row)" :key="line" class="block font-semibold text-slate-700">{{ line }}</span>
                  <span v-for="line in correctionLines(row)" :key="line.label" data-testid="ha-correction" class="block text-slate-700">
                    ✏️ {{ line.label }} :
                    <s>{{ line.helloasso || "—" }}</s>
                    →
                    <b>{{ line.value || "—" }}</b>
                  </span>
                  <ul v-if="row.issues.length" class="mt-1 space-y-0.5">
                    <li
                      v-for="issue in row.issues"
                      :key="`${issue.field}-${issue.code}`"
                      data-testid="ha-issue"
                      :class="issue.blocking ? 'font-semibold text-red-700' : 'text-amber-700'"
                    >
                      {{ issue.blocking ? "⛔" : "⚠️" }} {{ issue.message }}
                    </li>
                  </ul>
                  <select
                    v-if="needsIdentityChoice(row)"
                    data-testid="ha-review-choice"
                    :value="selectValue(choices[row.item_id]?.choice ?? '')"
                    :aria-label="`Choix pour ${personLabel(row)}`"
                    class="mt-1 block w-full rounded-md border border-slate-300 px-1.5 py-1 text-xs text-slate-800"
                    @change="choose(row.item_id, ($event.target as HTMLSelectElement).value)"
                  >
                    <option value="" disabled>— Choisir… —</option>
                    <option v-for="option in reviewOptions(row)" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                  <AttachPicker
                    v-if="canAttach(row) && choices[row.item_id]?.choice.startsWith(ATTACH)"
                    :members="preview.members"
                    :member-id="attachedMemberId(choices[row.item_id]?.choice ?? '')"
                    :comment="choices[row.item_id]?.comment ?? ''"
                    :person="personLabel(row)"
                    :cancellable="!needsIdentityChoice(row)"
                    @pick="(memberId) => pickMember(row.item_id, memberId)"
                    @comment="(text) => setComment(row.item_id, text)"
                    @cancel="choose(row.item_id, 'import')"
                  />
                  <button
                    v-else-if="canAttach(row) && !needsIdentityChoice(row)"
                    type="button"
                    data-testid="ha-attach-open"
                    title="Inscription faite au nom d'une autre personne (un parent pour son enfant) : la rattacher à un adhérent"
                    class="mt-1 block text-blue-700 underline"
                    @click="choose(row.item_id, ATTACH)"
                  >
                    🔗 Rattacher…
                  </button>
                  <button
                    v-if="canCorrect(row)"
                    type="button"
                    data-testid="ha-fix-open"
                    class="mt-1 block text-blue-700 underline"
                    @click="fixingId = row.item_id"
                  >
                    ✏️ Corriger…
                  </button>
                  <button
                    v-if="canRequest(row)"
                    type="button"
                    data-testid="ha-request-open"
                    class="mt-1 block text-blue-700 underline"
                    @click="requestPicked = [row.item_id]"
                  >
                    📧 Demander une correction…
                  </button>
                  <p v-if="rowProblem(row, preview, choices)" data-testid="ha-row-problem" class="mt-1 font-semibold text-red-700">
                    {{ rowProblem(row, preview, choices) }}
                  </p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>

      <CorrectionRequestDialog
        v-if="requestPicked"
        v-model:open="requestOpen"
        :rows="requestable"
        :picked="requestPicked"
        :campaign="campaign"
      />
      <CorrectionDialog
        v-if="fixingRow"
        v-model:open="fixingOpen"
        :row="fixingRow"
        :campaign="campaign"
        :move="move"
        @updated="corrected"
      />

      <div v-if="!preview.blocked_reason" class="flex flex-wrap items-center justify-between gap-2.5 border-t border-slate-200 pt-3">
        <UiButton
          data-testid="ha-import-apply"
          :disabled="!online || !!busy || !selectedCount || !!incompleteCount"
          :busy="busy === 'import' && 'Import en cours…'"
          @click="apply"
        >
          ✅ Importer la sélection
        </UiButton>
        <span data-testid="ha-import-selected" class="text-xs text-slate-500">
          {{ selectedCount }} inscription(s) sélectionnée(s)
          <b v-if="incompleteCount" class="text-red-700">· {{ incompleteCount }} rattachement(s) à compléter</b>
        </span>
      </div>
    </div>
  </UiCard>
</template>
