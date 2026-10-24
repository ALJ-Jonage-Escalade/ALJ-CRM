<script setup lang="ts">
/* « HelloAsso » (coaches and admins, online): the payments of the annual campaign, linked to a competitor or waiting
   for a coach. « Synchroniser » reads the campaign again from HelloAsso and links what it can by itself. */
import { computed, inject, ref, watch } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import { CLIENT_KEY, unwrap } from "../../lib/client";
import AttachForm from "./AttachForm.vue";
import { euros, type Competition, type MemberSlot } from "./competitions";
import {
  displayName,
  filterItems,
  isIgnored,
  isLinked,
  itemCounts,
  itemInfo,
  syncMessage,
  type HelloAssoItem,
  type ItemFilter,
} from "./helloasso";
import { WRITER_KEY } from "./writer";

const props = defineProps<{
  items: readonly HelloAssoItem[] | null;
  loading: boolean;
  competitions: readonly Competition[];
  members: readonly MemberSlot[];
}>();
const emit = defineEmits<{ changed: [] }>();
const client = inject(CLIENT_KEY)!;
const writer = inject(WRITER_KEY)!;

const HIDE_KEY = "alj_ha_hide_ignored"; // same choice as on the former page
function readHide(): boolean {
  try {
    return localStorage.getItem(HIDE_KEY) !== "0";
  } catch {
    return true;
  }
}
const filter = ref<ItemFilter>("unlinked");
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
const compName = computed(() => new Map(props.competitions.map((c) => [c.id, c.nom])));
const memberName = computed(() => new Map(props.members.map((m) => [m.id, `${m.nom} ${m.prenom}`])));
const FILTERS = computed(() => [
  { id: "unlinked" as const, label: "⚠️ En attente", n: count.value.unlinked },
  { id: "linked" as const, label: "✅ Rattachés", n: count.value.linked },
  { id: "ignored" as const, label: "🚫 Ignorés", n: count.value.ignored },
  { id: "all" as const, label: "📋 Tous", n: hideIgnored.value ? count.value.all - count.value.ignored : count.value.all },
]);

const syncing = ref(false);
async function sync(): Promise<void> {
  syncing.value = true;
  try {
    const answer = await writer.run(() => unwrap(client.POST("/api/helloasso/sync")));
    if (answer) writer.toast(syncMessage(answer), answer.status === "success" ? 5000 : 9000);
    emit("changed");
  } finally {
    syncing.value = false;
  }
}

const open = ref<HelloAssoItem | null>(null);
const dialogOpen = computed({ get: () => !!open.value, set: (v) => (open.value = v ? open.value : null) });

function firstWaiting(): void {
  const waiting = all.value.find((it) => !isLinked(it) && !isIgnored(it));
  if (waiting) open.value = waiting;
  else writer.toast("🎉 Aucun paiement en attente de rattachement !");
}

async function link(competitionId: number | null, adherentId: number | null, comment: string): Promise<void> {
  const it = open.value!;
  const both = competitionId != null && adherentId != null;
  const answer = await writer.run(
    () =>
      unwrap(
        client.PUT("/api/helloasso/items/{id_item}/link", {
          params: { path: { id_item: it.id_item } },
          body: { competition_id: competitionId, adherent_id: adherentId, commentaire: comment },
        }),
      ),
    { done: both ? "✅ Paiement HelloAsso rattaché avec succès !" : "💾 Enregistré (paiement non rattaché)." },
  );
  if (answer) close();
}

async function ignore(ignoreIt: boolean, note: string): Promise<void> {
  const it = open.value!;
  const body = ignoreIt ? { ignore: true, motif: note, commentaire: note } : { ignore: false, commentaire: note };
  const answer = await writer.run(
    () => unwrap(client.PUT("/api/helloasso/items/{id_item}/ignore", { params: { path: { id_item: it.id_item } }, body })),
    { done: ignoreIt ? "🚫 Ligne ignorée." : "↩️ La ligne n'est plus ignorée." },
  );
  if (answer) close();
}

function close(): void {
  open.value = null;
  emit("changed");
}

const DATE = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short" });
const day = (s: string) => (s && !Number.isNaN(Date.parse(s)) ? DATE.format(new Date(s)) : "—");
const chip = (active: boolean) => [
  "cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold",
  active ? "border-accent bg-accent text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
];
</script>

<template>
  <section aria-label="Paiements HelloAsso" data-testid="helloasso-pane">
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
      <UiButton variant="muted" data-testid="ha-first" @click="firstWaiting">🔗 Rattacher le premier en attente</UiButton>
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
      <label class="ml-auto inline-flex items-center gap-1.5 text-xs text-slate-600"
        ><input v-model="hideIgnored" type="checkbox" data-testid="ha-hide-ignored" /> Masquer les ignorés dans « Tous »</label
      >
    </div>
    <p class="mb-2 text-xs text-slate-500" data-testid="ha-count">
      {{
        items
          ? `${shown.length} paiement${shown.length > 1 ? "s" : ""}`
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
            <span class="block text-xs text-slate-500"
              >Commande <b>#{{ itemInfo(it).orderId || "—" }}</b> · 📅 {{ day(itemInfo(it).date) }}</span
            >
          </span>
          <span class="text-right">
            <b class="block text-[15px]">{{ euros(it.montant) }}</b>
            <span
              :class="[
                'inline-block rounded-full px-2 py-0.5 text-[10.5px] font-bold text-white',
                isLinked(it) ? 'bg-green-600' : isIgnored(it) ? 'bg-slate-400' : 'bg-amber-500',
              ]"
              data-testid="ha-state"
            >
              {{ isLinked(it) ? "✅ Rattaché" : isIgnored(it) ? "🚫 Ignoré" : "⚠️ En attente" }}
            </span>
          </span>
        </div>
        <div class="mt-1.5 rounded-md bg-slate-50 px-2 py-1.5 text-xs text-slate-600">
          <template v-if="itemInfo(it).fields.length">
            <div v-for="(f, i) in itemInfo(it).fields" :key="i">
              {{ f.name }} : <b class="text-slate-800">{{ f.answer || "—" }}</b>
            </div>
          </template>
          <template v-else>
            <div>
              🪪 Licence saisie : <b class="text-slate-800">{{ it.licence_saisie || "— non renseignée —" }}</b>
            </div>
            <div>
              🏆 Compétition saisie : <b class="text-slate-800">{{ it.competition_saisie || "— non renseignée —" }}</b>
            </div>
          </template>
          <div v-if="it.commentaire" class="mt-0.5 italic">💬 {{ it.commentaire }}</div>
        </div>
        <div class="mt-1.5 flex items-center justify-between gap-2 text-xs">
          <span class="min-w-0">
            <template v-if="isLinked(it)">
              <b>Épreuve :</b> {{ compName.get(it.competition_id!) ?? `#${it.competition_id}` }} · <b>Athlète :</b>
              {{ memberName.get(it.adherent_id!) ?? `#${it.adherent_id}` }}
              <span class="text-slate-500">({{ it.source || "auto" }})</span>
            </template>
            <span v-else-if="isIgnored(it)" class="text-slate-500"
              >🚫 Ignoré<template v-if="it.ignored_by"> par {{ it.ignored_by }}</template
              ><template v-if="it.ignore_motif"> · {{ it.ignore_motif }}</template></span
            >
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

    <UiDialog v-model:open="dialogOpen" title="🔗 Paiement HelloAsso" wide data-testid="attach-dialog">
      <AttachForm
        v-if="open"
        :key="open.id_item"
        :item="open"
        :competitions="competitions"
        :members="members"
        :busy="writer.busy.value"
        @link="link"
        @ignore="ignore"
        @cancel="open = null"
      />
    </UiDialog>
  </section>
</template>
