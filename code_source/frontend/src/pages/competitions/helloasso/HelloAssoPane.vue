<script setup lang="ts">
/* HelloAsso view */
import { computed, inject, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import UiBadge from "../../../components/ui/UiBadge.vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiDialog from "../../../components/ui/UiDialog.vue";
import { useMediaQuery } from "../../../composables/media";
import { CLIENT_KEY } from "../../../lib/client";
import { createCompetitionsApi } from "../../../services/competitions";
import { createIntegrationsApi } from "../../../services/integrations";
import { formatDate, formatEuros, parseDate } from "../../../lib/format";
import AttachForm from "./AttachForm.vue";
import { type Competition, type MemberSlot } from "../competitions";
import {
  displayName,
  filterItems,
  isIgnored,
  isLinked,
  itemCounts,
  itemInfo,
  nextPending,
  passSummary,
  pendingIds,
  suggestedCompetition,
  syncMessage,
  type HelloAssoItem,
  type ItemFilter,
  type ItemInfo,
  type PassTally,
} from "./helloasso";
import { WRITER_KEY } from "../writer";
import { plural } from "../../../lib/text";

const props = defineProps<{
  items: readonly HelloAssoItem[] | null;
  loading: boolean;
  competitions: readonly Competition[];
  members: readonly MemberSlot[];
  /** Address of the competitions list (the page's index route), where a competition opens. */
  listPath: string;
}>();
const emit = defineEmits<{ changed: [] }>();
const client = inject(CLIENT_KEY)!;
const competitionsApi = createCompetitionsApi(client);
const integrationsApi = createIntegrationsApi(client);
const writer = inject(WRITER_KEY)!;
const wide = useMediaQuery("(min-width: 1280px)");

const HIDE_KEY = "alj_ha_hide_ignored"; // same choice as on the former page
function readHide(): boolean {
  try {
    return localStorage.getItem(HIDE_KEY) !== "0";
  } catch {
    return true;
  }
}
const filter = ref<ItemFilter>("all");
const hideIgnored = ref(readHide());
watch(hideIgnored, (v) => {
  try {
    localStorage.setItem(HIDE_KEY, v ? "1" : "0");
  } catch {
    // blocked storage: the choice lasts as long as the page
  }
});
const search = ref("");

const all = computed(() => props.items ?? []);
const count = computed(() => itemCounts(all.value));
const shown = computed(() => filterItems(all.value, filter.value, hideIgnored.value, search.value, props.competitions, props.members));
// detected: the competition matching what the payer typed (a guess, unlike competition_id), linked from the row
const shownRows = computed(() =>
  shown.value.map((it) => ({ it, info: itemInfo(it), detected: suggestedCompetition(it, props.competitions) })),
);
const totalAmount = computed(() => all.value.reduce((sum, it) => sum + Number(it.montant ?? 0), 0));
const compName = computed(() => new Map(props.competitions.map((c) => [c.id, c.nom])));
const memberName = computed(() => new Map(props.members.map((m) => [m.id, `${m.nom} ${m.prenom}`])));
const FILTERS = computed(() => [
  { id: "all" as const, label: "📋 Tous", n: hideIgnored.value ? count.value.all - count.value.ignored : count.value.all },
  { id: "unlinked" as const, label: "⚠️ En attente", n: count.value.unlinked },
  { id: "linked" as const, label: "✅ Rattachés", n: count.value.linked },
  { id: "ignored" as const, label: "🚫 Ignorés", n: count.value.ignored },
]);

const syncing = ref(false);
async function sync(): Promise<void> {
  syncing.value = true;
  try {
    const answer = await writer.run(() => integrationsApi.syncHelloAsso());
    if (answer) {
      writer.toast(syncMessage(answer), answer.status === "success" ? 5000 : 9000);
    }
    emit("changed");
  } finally {
    syncing.value = false;
  }
}

const open = ref<HelloAssoItem | null>(null);
const dialogOpen = computed({
  get: () => !!open.value,
  set: (v) => {
    if (!v) {
      stop();
    }
  },
});

/* Linking pass: the pending payments of the list shown, one after another. Each decision is saved at once; the pass
   only chooses what the dialog shows next. A row's own button opens that payment alone (no pass). */
interface Pass {
  ids: number[];
  position: number;
  tally: PassTally;
}
const pass = ref<Pass | null>(null);
const pending = computed(() => pendingIds(shown.value));
const dialogTitle = computed(() =>
  pass.value ? `🔗 Paiement HelloAsso — ${pass.value.position + 1} / ${pass.value.ids.length}` : "🔗 Paiement HelloAsso",
);

function startPass(): void {
  if (!pending.value.length) {
    writer.toast(
      count.value.unlinked ? "Aucun paiement en attente dans la liste affichée." : "🎉 Aucun paiement en attente de rattachement !",
    );
    return;
  }
  pass.value = { ids: pending.value, position: -1, tally: { linked: 0, saved: 0, ignored: 0, skipped: 0 } };
  advance();
}

/** Shows the next payment of the pass, or ends it. The payment saved just before is behind: the list reloads meanwhile. */
function advance(): void {
  const current = pass.value!;
  const position = nextPending(current.ids, current.position, all.value);
  const next = position < 0 ? undefined : all.value.find((it) => it.id_item === current.ids[position]);
  if (next) {
    current.position = position;
    open.value = next;
  } else {
    stop();
  }
}

function skip(): void {
  pass.value!.tally.skipped++;
  advance();
}

/** Closes the dialog; ending a pass tells what it did. */
function stop(): void {
  const summary = pass.value && passSummary(pass.value.tally);
  pass.value = null;
  open.value = null;
  if (summary) {
    writer.toast(summary, 6000);
  }
}

/** After a saved decision: the next payment of the pass, else the dialog closes. */
function decided(outcome: keyof PassTally): void {
  emit("changed");
  if (pass.value) {
    pass.value.tally[outcome]++;
    advance();
  } else {
    open.value = null;
  }
}

async function link(competitionId: number | null, adherentId: number | null, comment: string): Promise<void> {
  const it = open.value!;
  const both = competitionId != null && adherentId != null;
  const answer = await writer.run(
    () => competitionsApi.linkPayment(it.id_item, { competition_id: competitionId, adherent_id: adherentId, commentaire: comment }),
    { done: both ? "✅ Paiement HelloAsso rattaché avec succès !" : "💾 Enregistré (paiement non rattaché)." },
  );
  if (answer) {
    decided(both ? "linked" : "saved");
  }
}

async function ignore(ignoreIt: boolean, note: string): Promise<void> {
  const it = open.value!;
  const body = ignoreIt ? { ignore: true, motif: note, commentaire: note } : { ignore: false, commentaire: note };
  const answer = await writer.run(() => competitionsApi.ignorePayment(it.id_item, body), {
    done: ignoreIt ? "🚫 Ligne ignorée." : "↩️ La ligne n'est plus ignorée.",
  });
  if (answer) {
    decided(ignoreIt ? "ignored" : "saved");
  }
}

function payer(it: HelloAssoItem, info: ItemInfo): string {
  return info.payerName || `${it.payer_prenom ?? ""} ${it.payer_nom ?? ""}`.trim() || "—";
}

function day(text: string): string {
  const date = parseDate(text);
  return date ? formatDate(date) : "—";
}
const chip = (active: boolean) => [
  "cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold",
  active ? "border-accent bg-accent text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
];
</script>

<template>
  <section aria-label="Paiements HelloAsso" data-testid="helloasso-pane">
    <div v-if="wide" class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="m-0 text-[17px] font-bold text-slate-800">🧾 Paiements HelloAsso & Rapprochement</h2>
          <p class="mt-1 text-[12.5px] text-slate-500">
            Articles réglés sur la campagne HelloAsso et état de rattachement aux épreuves et compétiteurs.
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <UiButton small data-testid="ha-sync" :busy="syncing && 'Synchro…'" @click="sync">
            🔄 Lancer la synchronisation HelloAsso
          </UiButton>
          <UiButton variant="muted" small data-testid="ha-first" @click="startPass">
            🔗 Rattacher les paiements en attente ({{ pending.length }})
          </UiButton>
        </div>
      </div>
      <div class="mb-3.5 grid grid-cols-5 gap-2.5">
        <div
          v-for="k in [
            { l: 'Total paiements', v: count.all, c: 'text-slate-800' },
            { l: 'Rattachés', v: count.linked, c: 'text-green-600' },
            { l: 'En attente', v: count.unlinked, c: 'text-amber-600' },
            { l: 'Ignorés', v: count.ignored, c: 'text-slate-500' },
            { l: 'Montant total collecté', v: formatEuros(totalAmount), c: 'text-blue-600' },
          ]"
          :key="k.l"
          class="rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-center"
        >
          <div :class="['text-xl font-extrabold', k.c]">{{ k.v }}</div>
          <div class="mt-0.5 text-[11px] font-semibold text-slate-500 uppercase">{{ k.l }}</div>
        </div>
      </div>
      <div class="mb-2.5 flex flex-wrap items-center justify-between gap-2.5">
        <input
          v-model="search"
          type="search"
          data-testid="ha-search"
          placeholder="Rechercher (nom, commande, licence…)"
          class="w-full max-w-120 flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px]"
        />
        <div class="flex flex-wrap items-center gap-3">
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="f in FILTERS"
              :key="f.id"
              type="button"
              :data-testid="`ha-filter-${f.id}`"
              :aria-pressed="filter === f.id"
              :class="chip(filter === f.id)"
              @click="filter = f.id"
            >
              {{ f.label }} ({{ f.n }})
            </button>
          </div>
          <label class="inline-flex items-center gap-1.5 text-xs text-slate-600">
            <input v-model="hideIgnored" type="checkbox" data-testid="ha-hide-ignored" />
            Masquer les ignorés dans « Tous »
          </label>
        </div>
      </div>
      <p v-if="!items" class="mb-2 text-xs text-slate-500" data-testid="ha-count">
        {{ loading ? "⏳ Chargement des paiements…" : "Paiements HelloAsso indisponibles (réseau ?)." }}
      </p>
      <div class="overflow-x-auto rounded-lg border border-slate-200">
        <table class="w-full border-collapse text-left text-[13px]" aria-label="Paiements HelloAsso">
          <thead class="bg-slate-50 text-[11px] font-bold whitespace-nowrap text-slate-500 uppercase">
            <tr>
              <th class="px-2.5 py-2">Date</th>
              <th class="px-2.5 py-2">Commande</th>
              <th class="px-2.5 py-2">Payeur</th>
              <th class="px-2.5 py-2">Athlète / Licence saisie</th>
              <th class="px-2.5 py-2">Épreuve détectée</th>
              <th class="px-2.5 py-2">Montant</th>
              <th class="px-2.5 py-2">Compétition rattachée</th>
              <th class="px-2.5 py-2">Commentaire</th>
              <th class="px-2.5 py-2">Source</th>
              <th class="px-2.5 py-2 text-center">Action</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="{ it, info, detected } in shownRows"
              :key="it.id_item"
              data-testid="ha-item"
              :class="['border-t border-slate-100 align-top', isIgnored(it) && 'bg-slate-50 opacity-75']"
            >
              <td class="px-2.5 py-2 whitespace-nowrap text-slate-500">{{ day(info.date) }}</td>
              <td class="px-2.5 py-2 whitespace-nowrap">
                <b>#{{ info.orderId || "—" }}</b>
              </td>
              <td class="px-2.5 py-2">
                <div class="font-semibold text-slate-800">{{ payer(it, info) }}</div>
                <div v-if="info.payerEmail" class="text-[11px] text-slate-500">{{ info.payerEmail }}</div>
              </td>
              <td class="px-2.5 py-2">
                <div class="font-semibold">{{ displayName(it, info) }}</div>
                <div class="text-[11px] text-slate-500">Licence : {{ it.licence_saisie || "—" }}</div>
              </td>
              <td class="px-2.5 py-2 text-slate-600">
                <RouterLink
                  v-if="detected != null"
                  :to="{ path: listPath, query: { id: String(detected) } }"
                  :title="`Compétition détectée : ${compName.get(detected)}`"
                  data-testid="ha-detected"
                  class="text-accent no-underline hover:underline"
                >
                  {{ it.competition_saisie || info.itemName || compName.get(detected) }}
                </RouterLink>
                <template v-else>{{ it.competition_saisie || info.itemName || "—" }}</template>
              </td>
              <td class="px-2.5 py-2 whitespace-nowrap">
                <b>{{ formatEuros(it.montant) }}</b>
              </td>
              <td class="px-2.5 py-2">
                <UiBadge :color="isLinked(it) ? 'blue' : isIgnored(it) ? 'slate' : 'amber'" data-testid="ha-state">
                  <template v-if="isLinked(it)">
                    ✅
                    <RouterLink
                      v-if="compName.has(it.competition_id!)"
                      :to="{ path: listPath, query: { id: String(it.competition_id) } }"
                      data-testid="ha-linked-competition"
                      class="text-inherit no-underline hover:underline"
                    >
                      {{ compName.get(it.competition_id!) }}
                    </RouterLink>
                    <template v-else>#{{ it.competition_id }}</template>
                  </template>
                  <template v-else-if="isIgnored(it)">🚫 Ignoré{{ it.ignore_motif ? ` (${it.ignore_motif})` : "" }}</template>
                  <template v-else>⚠️ En attente</template>
                </UiBadge>
                <div v-if="it.commentaire" class="mt-0.5 text-[11px] text-slate-500 italic">💬 {{ it.commentaire }}</div>
              </td>
              <td class="px-2.5 py-2">
                <span v-if="it.adherent_id != null" class="font-semibold text-slate-800"></span>
                <span v-else-if="isIgnored(it)" class="text-[11px] text-slate-500 italic">
                  Écarté
                  <template v-if="it.ignored_by">par {{ it.ignored_by }}</template>
                </span>
                <span v-else class="text-[11px] text-slate-500">En attente</span>
              </td>
              <td class="px-2.5 py-2">
                <UiBadge :color="isLinked(it) ? 'green' : isIgnored(it) ? 'slate' : 'amber'">
                  {{ isIgnored(it) ? "ignoré" : it.source || (isLinked(it) ? "manuel" : "attente") }}
                </UiBadge>
              </td>
              <td class="px-2.5 py-2 text-center whitespace-nowrap">
                <UiButton :variant="isLinked(it) || isIgnored(it) ? 'muted' : 'primary'" small data-testid="ha-open" @click="open = it">
                  {{ isLinked(it) ? "🔗 Modifier" : isIgnored(it) ? "🔍 Voir / Réactiver" : "🔗 Rattacher" }}
                </UiButton>
              </td>
            </tr>
            <tr v-if="items && !shown.length">
              <td colspan="10" class="px-4 py-6 text-center text-slate-500">
                Aucun paiement HelloAsso
                {{ filter === "unlinked" ? "en attente de rattachement" : filter === "ignored" ? "ignoré" : "trouvé" }}.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <template v-else>
      <div class="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div
          v-for="k in [
            { l: 'Paiements', v: count.all, c: 'text-slate-800' },
            { l: 'Rattachés', v: count.linked, c: 'text-green-600' },
            { l: 'En attente', v: count.unlinked, c: 'text-amber-600' },
            { l: 'Ignorés', v: count.ignored, c: 'text-slate-500' },
          ]"
          :key="k.l"
          class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-center"
        >
          <div :class="['text-xl font-extrabold', k.c]">{{ k.v }}</div>
          <div class="text-[11px] font-semibold text-slate-500">{{ k.l }}</div>
        </div>
      </div>
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <UiButton data-testid="ha-sync" :busy="syncing && 'Synchro…'" @click="sync">🔄 Synchroniser</UiButton>
        <UiButton variant="muted" data-testid="ha-first" @click="startPass">
          🔗 Rattacher les paiements en attente ({{ pending.length }})
        </UiButton>
        <input
          v-model="search"
          type="search"
          data-testid="ha-search"
          placeholder="Rechercher (nom, commande, licence…)"
          class="min-w-48 flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px]"
        />
      </div>
      <div class="mb-2 flex flex-wrap items-center gap-1.5">
        <button
          v-for="f in FILTERS"
          :key="f.id"
          type="button"
          :data-testid="`ha-filter-${f.id}`"
          :aria-pressed="filter === f.id"
          :class="chip(filter === f.id)"
          @click="filter = f.id"
        >
          {{ f.label }} ({{ f.n }})
        </button>
        <label class="ml-auto inline-flex items-center gap-1.5 text-xs text-slate-600">
          <input v-model="hideIgnored" type="checkbox" data-testid="ha-hide-ignored" />
          Masquer les ignorés dans « Tous »
        </label>
      </div>
      <p class="mb-2 text-xs text-slate-500" data-testid="ha-count">
        {{
          items
            ? `${shown.length} paiement${plural(shown.length)}`
            : loading
              ? "⏳ Chargement des paiements…"
              : "Paiements HelloAsso indisponibles (réseau ?)."
        }}
      </p>

      <ul class="grid gap-2 xl:grid-cols-2">
        <li
          v-for="it in shown"
          :key="it.id_item"
          data-testid="ha-item"
          :class="[
            'rounded-xl border border-l-4 border-slate-200 bg-white px-3.5 py-2.5 shadow-sm',
            isLinked(it) ? 'border-l-green-600' : isIgnored(it) ? 'border-l-slate-400 opacity-75' : 'border-l-red-500',
          ]"
        >
          <div class="flex items-start justify-between gap-2">
            <span class="min-w-0">
              <b class="block text-[14.5px]">{{ displayName(it) }}</b>
              <span class="block text-xs text-slate-500">
                Commande
                <b>#{{ itemInfo(it).orderId || "—" }}</b>
                · 📅 {{ day(itemInfo(it).date) }}
              </span>
            </span>
            <span class="text-right">
              <b class="block text-[15px]">{{ formatEuros(it.montant) }}</b>
              <UiBadge :color="isLinked(it) ? 'green' : isIgnored(it) ? 'slate' : 'amber'" data-testid="ha-state">
                {{ isLinked(it) ? "✅ Rattaché" : isIgnored(it) ? "🚫 Ignoré" : "⚠️ En attente" }}
              </UiBadge>
            </span>
          </div>
          <div class="mt-1.5 rounded-md bg-slate-50 px-2 py-1.5 text-xs text-slate-600">
            <template v-if="itemInfo(it).fields.length">
              <div v-for="(f, i) in itemInfo(it).fields" :key="i">
                {{ f.name }} :
                <b class="text-slate-800">{{ f.answer || "—" }}</b>
              </div>
            </template>
            <template v-else>
              <div>
                🪪 Licence saisie :
                <b class="text-slate-800">{{ it.licence_saisie || "— non renseignée —" }}</b>
              </div>
              <div>
                🏆 Compétition saisie :
                <b class="text-slate-800">{{ it.competition_saisie || "— non renseignée —" }}</b>
              </div>
            </template>
            <div v-if="it.commentaire" class="mt-0.5 italic">💬 {{ it.commentaire }}</div>
          </div>
          <div class="mt-1.5 flex items-center justify-between gap-2 text-xs">
            <span class="min-w-0">
              <template v-if="isLinked(it)">
                <b>Épreuve :</b>
                <RouterLink
                  v-if="compName.has(it.competition_id!)"
                  :to="{ path: listPath, query: { id: String(it.competition_id) } }"
                  data-testid="ha-linked-competition"
                  class="text-accent no-underline hover:underline"
                >
                  {{ compName.get(it.competition_id!) }}
                </RouterLink>
                <template v-else>#{{ it.competition_id }}</template>
                ·
                <b>Athlète :</b>
                {{ memberName.get(it.adherent_id!) ?? `#${it.adherent_id}` }}
                <span class="text-slate-500">({{ it.source || "auto" }})</span>
              </template>
              <span v-else-if="isIgnored(it)" class="text-slate-500">
                🚫 Ignoré
                <template v-if="it.ignored_by">par {{ it.ignored_by }}</template>
                <template v-if="it.ignore_motif">· {{ it.ignore_motif }}</template>
              </span>
              <span v-else class="font-semibold text-red-600">⚠️ À attribuer à une compétition et un athlète</span>
            </span>
            <UiButton :variant="isLinked(it) || isIgnored(it) ? 'muted' : 'primary'" small data-testid="ha-open" @click="open = it">
              {{ isLinked(it) ? "🔗 Modifier" : isIgnored(it) ? "🔍 Détails" : "🔗 Rattacher" }}
            </UiButton>
          </div>
        </li>
        <li v-if="items && !shown.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">
          Aucun paiement HelloAsso {{ filter === "unlinked" ? "en attente de rattachement" : filter === "ignored" ? "ignoré" : "trouvé" }}.
        </li>
      </ul>
    </template>

    <UiDialog v-model:open="dialogOpen" :title="dialogTitle" wide data-testid="attach-dialog">
      <AttachForm
        v-if="open"
        :key="open.id_item"
        :item="open"
        :competitions="competitions"
        :members="members"
        :busy="writer.busy.value"
        :skippable="!!pass"
        @link="link"
        @ignore="ignore"
        @cancel="stop"
        @skip="skip"
      />
    </UiDialog>
  </section>
</template>
