<script setup lang="ts">
/* Compétitions (/competitions and /bureau/competitions, any role: read-only accounts too, as on the former phone
   page). Coaches and admins change everything here. */
import { computed, inject, onScopeDispose, provide, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import AppShell from "../components/AppShell.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiDialog from "../components/ui/UiDialog.vue";
import UiToast from "../components/ui/UiToast.vue";
import { AUTH_KEY } from "../composables/auth";
import { useSyncedResource } from "../composables/syncedResource";
import { useToast } from "../composables/toast";
import { pageVerdict } from "../lib/access";
import { formatDateTime } from "../lib/format";
import { CLIENT_KEY, type Schemas } from "../lib/client";
import { createCompetitionsApi } from "../services/competitions";
import { isStaff } from "../lib/roles";
import { offlineStore, STORE_KEY } from "../lib/store";
import BalancePane from "./competitions/balance/BalancePane.vue";
import CoachesPane from "./competitions/CoachesPane.vue";
import CompetitionDetail from "./competitions/detail/CompetitionDetail.vue";
import CompetitionForm from "./competitions/CompetitionForm.vue";
import {
  participantRows,
  period,
  sortCompetitions,
  todayIso,
  toMemberSlots,
  type Coach,
  type Competition,
  type CompetitorContact,
  type MemberSlot,
} from "./competitions/competitions";
import HelloAssoPane from "./competitions/helloasso/HelloAssoPane.vue";
import type { HelloAssoItem } from "./competitions/helloasso/helloasso";
import CompetitionCalendar from "./competitions/list/CompetitionCalendar.vue";
import CompetitionCards from "./competitions/list/CompetitionCards.vue";
import CompetitionFilters from "./competitions/list/CompetitionFilters.vue";
import CompetitionStats from "./competitions/list/CompetitionStats.vue";
import CompetitionTable from "./competitions/list/CompetitionTable.vue";
import { useCompetitionFilters, type ViewMode } from "./competitions/list/filters";
import ViewSwitcher from "./competitions/list/ViewSwitcher.vue";
import { createOutbox, pendingLine, replayMessage } from "./competitions/outbox";
import { createWriter, WRITER_KEY } from "./competitions/writer";
import { plural } from "../lib/text";
import { dialogs } from "../composables/dialogs";

const auth = inject(AUTH_KEY)!;
const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
const store = inject(STORE_KEY, null) ?? offlineStore();
const route = useRoute();
const router = useRouter();
const toast = useToast();

const access = computed(() => pageVerdict(auth.state.value, "competitions"));
const open = computed(() => access.value === "allow" || access.value === "offline");
const uid = computed(() => {
  const authState = auth.state.value;
  return open.value && (authState.status === "signedIn" || authState.status === "error") ? authState.user.uid : null;
});
const signedIn = computed(() => auth.state.value.status === "signedIn");
// Coaches and admins see the contacts; offline the role is unknown: only a copy kept for this user can show
const staff = computed(() => auth.state.value.status === "signedIn" && isStaff(auth.state.value.role));
const contactsShown = computed(() => staff.value || access.value === "offline");

const competitions = useSyncedResource<Competition[]>("competitions", () => (open.value ? "/api/competitions" : null), {
  offline: true,
  uid,
});
const competitors = useSyncedResource<CompetitorContact[]>(
  "competitors",
  () => (open.value && contactsShown.value ? "/api/members/competitors" : null),
  { offline: true, uid },
);
// Offline the role cannot be checked: a device keeping the contacts is a coach's (they are never kept for others)
const canWrite = computed(() => staff.value || (access.value === "offline" && competitors.data.value !== null));
// Tariffs and slot groups to group the participants, names and e-mails to add or write to them: online only
const members = useSyncedResource<MemberSlot[]>(
  "competition-members",
  () => (open.value && signedIn.value ? "/api/competition-members" : null),
  {
    offline: false,
    select: toMemberSlots,
    intervalMs: 60_000,
  },
);
const coaches = useSyncedResource<Coach[]>("coaches", () => (staff.value ? "/api/coaches" : null), { offline: false, intervalMs: 60_000 });

type Section = "competitions" | "helloasso" | "bilan" | "coachs";
const SECTIONS: { id: Section; label: string }[] = [
  { id: "competitions", label: "🏆 Compétitions" },
  { id: "helloasso", label: "💳 HelloAsso" },
  { id: "bilan", label: "📊 Bilan" },
  { id: "coachs", label: "🏃 Coachs" },
];
const section = computed<Section>(() => {
  const requested = route.query.section;
  return canWrite.value && SECTIONS.some((x) => x.id === requested) ? (requested as Section) : "competitions";
});
const items = useSyncedResource<HelloAssoItem[]>(
  "helloasso-items",
  () => (staff.value && section.value === "helloasso" ? "/api/helloasso/items" : null),
  { offline: false },
);

// ---------------------------------------------------------------- Network and outbox

const networkUp = ref(navigator.onLine);
const onNetwork = () => (networkUp.value = navigator.onLine);
window.addEventListener("online", onNetwork);
window.addEventListener("offline", onNetwork);
onScopeDispose(() => {
  window.removeEventListener("online", onNetwork);
  window.removeEventListener("offline", onNetwork);
});
const online = computed(() => {
  const authState = auth.state.value;
  return networkUp.value && competitions.state.value !== "offline" && !(authState.status === "error" && authState.offline);
});

const outbox = createOutbox(store, (competitionId, adherentId, body) => competitionsApi.updateParticipant(competitionId, adherentId, body));
watch(uid, (u) => void outbox.load(u), { immediate: true });

/* Sent as soon as the API answers again (each successful poll), oldest first. */
async function replay(): Promise<void> {
  if (!uid.value || !online.value || !outbox.changes.value.size) {
    return;
  }
  const result = await outbox.replay(uid.value);
  if (!result) {
    return;
  }
  if (result.denied) {
    // Role lost: nothing kept on the device, unsent changes included
    outbox.forget();
    await store.clearAll();
    toast.show("🔒 Accès refusé par le serveur : les modifications faites hors ligne n'ont pas été envoyées.", 9000);
    return;
  }
  toast.show(replayMessage(result), result.refused.length ? 15_000 : 4000);
  void competitions.refresh();
}

watch([() => competitions.checkedAt.value, uid, online, () => outbox.changes.value.size], () => void replay());

// ---------------------------------------------------------------- Writes

const writer = createWriter({
  online: () => online.value,
  apply: (doc) => {
    const list = competitions.data.value ?? [];
    competitions.set(list.some((c) => c.id === doc.id) ? list.map((c) => (c.id === doc.id ? doc : c)) : [doc, ...list]);
  },
  dropped: (id) => competitions.set((competitions.data.value ?? []).filter((c) => c.id !== id)),
  reload: () => {
    void competitions.refresh();
    void competitors.refresh();
    void items.refresh();
    void coaches.refresh();
  },
  toast: (m, ms) => toast.show(m, ms),
});
provide(WRITER_KEY, writer);

// ---------------------------------------------------------------- The list

const today = todayIso();
const all = computed(() => sortCompetitions(competitions.data.value ?? []));
const {
  search,
  when,
  selectedSeason,
  seasons,
  seasonCompetitions,
  current,
  archived: archivedCompetitions,
  calendar: calendarCompetitions,
  past: pastCompetitions,
  filtered,
} = useCompetitionFilters(all, today);
const viewMode = ref<ViewMode>("cards");

const selectedId = computed(() => (typeof route.query.id === "string" ? route.query.id : ""));
// The detail is shown next to the cards: a competition opened from the table or the calendar goes back to them (their
// open event covers the competition already selected, which leaves the URL unchanged)
watch(selectedId, (id) => {
  if (id) {
    viewMode.value = "cards";
  }
});
const selected = computed(() => all.value.find((c) => String(c.id) === selectedId.value));
const rows = computed(() =>
  selected.value
    ? participantRows(
        selected.value,
        members.data.value ?? [],
        contactsShown.value ? (competitors.data.value ?? []) : [],
        (id, flag) => outbox.pending(selected.value!.id, id, flag)?.value,
      )
    : [],
);

const creating = ref(false);
const editingCompetition = ref<Competition | null>(null);
const editDialogOpen = computed({
  get: () => Boolean(editingCompetition.value),
  set: (val: boolean) => {
    if (!val) {
      editingCompetition.value = null;
    }
  },
});

function openFromCalendar(c: Competition): void {
  viewMode.value = "cards";
  void router.push({ query: { id: String(c.id) } });
}

function editFromTable(c: Competition): void {
  editingCompetition.value = c;
}

async function saveFromTable(body: Schemas["CompetitionCreate"]): Promise<void> {
  if (!editingCompetition.value) {
    return;
  }
  const id = editingCompetition.value.id;
  const ok = await writer.run(() => competitionsApi.update(id, body), {
    done: "✅ Compétition mise à jour.",
  });
  if (ok) {
    editingCompetition.value = null;
  }
}

async function removeFromTable(c: Competition): Promise<void> {
  const ok = await dialogs.confirm({
    title: "Supprimer la compétition",
    message: `Supprimer définitivement « ${c.nom} » et sa liste de compétiteurs ?`,
    confirmLabel: "Supprimer",
    variant: "danger",
  });
  if (!ok) {
    return;
  }
  await writer.run(() => competitionsApi.remove(c.id), {
    done: "🗑 Compétition supprimée.",
  });
}

async function create(body: Schemas["CompetitionCreate"]): Promise<void> {
  const created = await writer.run(() => competitionsApi.create(body), { done: "✅ Compétition créée." });
  if (!created) {
    return;
  }
  creating.value = false;
  await router.push({ query: { id: String(created.id) } });
}

async function archivePastCompetitions(): Promise<void> {
  const pastCompetitionsList = pastCompetitions.value;
  const nbPastCompetitions = pastCompetitionsList.length;
  if (!nbPastCompetitions) {
    return;
  }
  if (
    !(await dialogs.confirm({
      title: "Archiver les compétitions passées",
      message: `Archiver ${nbPastCompetitions} compétition${plural(nbPastCompetitions)} passée${plural(nbPastCompetitions)} ?\n\n${pastCompetitionsList.map((competition) => `• ${competition.nom} (${period(competition)})`).join("\n")}\n\nElles resteront consultables dans les archives et comptées dans le bilan.`,
      confirmLabel: "Archiver",
    }))
  ) {
    return;
  }
  await writer.run(() => competitionsApi.archivePast(), {
    done: (r) => `📦 ${r.archived.length} compétition${plural(r.archived.length)} archivée${plural(r.archived.length)}.`,
  });
}

const listLine = computed(() => {
  if (!competitions.data.value) {
    return competitions.state.value === "loading" ? "⏳ Chargement des compétitions…" : "Aucune donnée des compétitions sur cet appareil.";
  }
  const currentCount = current.value.length;
  const archivedCount = archivedCompetitions.value.length;
  const archivedPart = archivedCount ? ` · ${archivedCount} archivée${plural(archivedCount)}` : "";
  return `${currentCount} compétition${plural(currentCount)}${archivedPart}`;
});

const syncInfo = computed(() => {
  const at = competitions.dataAt.value;
  const since = at ? ` — données du ${formatDateTime(at)}` : "";
  const state = competitions.state.value;
  const waiting = pendingLine(outbox.changes.value.size);
  if (competitions.httpStatus.value === 403) {
    return "🔒 Accès restreint";
  }
  if (state === "offline" || auth.state.value.status === "error") {
    return `📴 Hors ligne${since || " : aucune donnée sur cet appareil"}${waiting}`;
  }
  if (state === "error") {
    return `⚠️ Serveur injoignable — nouvel essai automatique${since}${waiting}`;
  }
  if (state === "loading") {
    return at ? `💾 Données du ${formatDateTime(at)}${waiting}` : waiting.slice(3);
  }
  return waiting.slice(3);
});

const tab = (active: boolean) => [
  "shrink-0 rounded-lg px-3 py-1.5 text-[13px] font-bold no-underline",
  active ? "bg-accent text-white" : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50",
];
</script>

<template>
  <AppShell page="competitions" title="Compétitions" :sync="syncInfo">
    <nav
      v-if="canWrite"
      aria-label="Sections des compétitions"
      class="mb-3 flex flex-wrap items-center justify-between gap-2"
      data-testid="sections"
    >
      <div class="flex gap-1.5 overflow-x-auto">
        <RouterLink
          v-for="s in SECTIONS"
          :key="s.id"
          :to="{ query: s.id === 'competitions' ? {} : { section: s.id } }"
          :data-testid="`section-${s.id}`"
          :aria-current="section === s.id ? 'page' : undefined"
          :class="tab(section === s.id)"
        >
          {{ s.label }}
        </RouterLink>
      </div>
      <UiButton small data-testid="create-comp" @click="online ? (creating = true) : writer.toast('📴 Hors ligne : création impossible.')">
        ➕ Ajouter une compétition
      </UiButton>
    </nav>

    <HelloAssoPane
      v-if="section === 'helloasso'"
      :items="items.data.value"
      :loading="items.state.value === 'loading'"
      :competitions="all"
      :members="members.data.value ?? []"
      @changed="items.refresh()"
    />
    <BalancePane v-else-if="section === 'bilan'" :competitions="all" />
    <CoachesPane v-else-if="section === 'coachs'" :coaches="coaches.data.value" :competitions="all" @changed="competitions.refresh()" />

    <!-- Mode de vue, sous les onglets (la vue Compétitions seulement ; masqué sur téléphone quand une fiche est ouverte) -->
    <template v-else>
      <div :class="['mb-3', selected ? 'hidden md:block' : '']">
        <ViewSwitcher v-model="viewMode" />
      </div>
      <div
        class="flex flex-col md:grid md:grid-cols-[minmax(0,340px)_minmax(0,1fr)] md:items-start md:gap-4 xl:grid-cols-[320px_minmax(0,1fr)] 2xl:grid-cols-[380px_minmax(0,1fr)]"
      >
        <!-- The competitions: always on desktop (a panel scrolling on its own), on phones until one is opened -->
        <section
          :class="[
            selected ? 'hidden md:block' : '',
            viewMode !== 'cards' ? 'md:col-span-2' : '',
            'order-2 md:order-1 md:col-start-1 md:row-start-1 md:sticky md:top-3 md:max-h-[calc(100dvh-1.5rem)] md:overflow-y-auto md:rounded-xl md:border md:border-slate-200 md:bg-white md:p-3 md:shadow-sm',
          ]"
          aria-label="Liste des compétitions"
        >
          <div v-if="canWrite && pastCompetitions.length" class="mb-2 flex flex-wrap gap-1.5">
            <UiButton variant="muted" small data-testid="archive-past" @click="archivePastCompetitions">
              📦 Archiver les passées ({{ pastCompetitions.length }})
            </UiButton>
          </div>

          <CompetitionFilters
            v-model:season="selectedSeason"
            v-model:search="search"
            v-model:when="when"
            :seasons="seasons"
            :calendar="viewMode === 'calendar'"
          />
          <p class="pt-1 pb-1 mb-2 text-xs text-slate-500" data-testid="comp-count">{{ listLine }}</p>

          <!-- Vue Tableau -->
          <div v-if="viewMode === 'table'" class="mb-3">
            <CompetitionTable
              :competitions="current"
              :can-write="canWrite"
              @open="viewMode = 'cards'"
              @edit="editFromTable"
              @remove="removeFromTable"
            />
          </div>

          <!-- Vue Calendrier -->
          <div v-else-if="viewMode === 'calendar'" class="mb-3">
            <CompetitionCalendar :competitions="calendarCompetitions" :selected-id="selectedId" @open="openFromCalendar" />
          </div>

          <!-- Vue Cartes (par défaut) -->
          <CompetitionCards
            v-else
            :competitions="current"
            :archived="archivedCompetitions"
            :loaded="competitions.data.value !== null"
            :filtered="filtered"
            :selected-id="selected?.id"
          />
        </section>

        <CompetitionDetail
          v-if="selected && viewMode === 'cards'"
          :key="selected.id"
          :competition="selected"
          :rows="rows"
          :members="members.data.value ?? []"
          :coaches="coaches.data.value ?? []"
          :can-write="canWrite"
          :staff="staff"
          :contacts-shown="contactsShown"
          :outbox="outbox"
          :uid="uid"
          class="order-1 min-w-0 md:order-2 md:col-start-2 md:row-start-1"
        />
        <div
          v-else-if="viewMode === 'cards'"
          class="order-1 flex min-w-0 flex-col gap-3 md:order-2 md:col-start-2 md:row-start-1"
          data-testid="stats-no-selection"
        >
          <CompetitionStats :competitions="seasonCompetitions" :today="today" />

          <div class="hidden rounded-xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-slate-500 md:block">
            <p class="m-0 text-sm font-medium">
              {{
                selectedId && competitions.data.value
                  ? "Compétition introuvable."
                  : "Sélectionnez une compétition dans la liste pour afficher ses détails et gérer ses compétiteurs."
              }}
            </p>
          </div>
        </div>
      </div>
    </template>

    <UiDialog v-model:open="creating" title="➕ Nouvelle compétition" wide data-testid="create-dialog">
      <CompetitionForm
        v-if="creating"
        :coaches="coaches.data.value ?? []"
        :busy="writer.busy.value"
        @save="create"
        @cancel="creating = false"
      />
    </UiDialog>

    <UiDialog v-model:open="editDialogOpen" :title="`✏️ Modifier : ${editingCompetition?.nom}`" wide data-testid="edit-dialog">
      <CompetitionForm
        v-if="editingCompetition"
        :competition="editingCompetition"
        :coaches="coaches.data.value ?? []"
        :busy="writer.busy.value"
        @save="saveFromTable"
        @cancel="editingCompetition = null"
      />
    </UiDialog>

    <UiToast :message="toast.message.value" />
  </AppShell>
</template>
