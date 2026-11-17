<script setup lang="ts">
/* One competition: its details, counters and competitors by slot group (a table on wide screens, cards elsewhere). Coaches and admins change it here (plan phase
   11): the competition itself, its results and exports (CompetitionActions), its list (add a member, load the
   competition group, remove the ones never invited), each competitor (ParticipantCard) and an e-mail to its competitors. « Participe » and « Présent » also change offline (the outbox, sent when the network comes back). */
import { computed, inject, ref } from "vue";
import { RouterLink } from "vue-router";
import UiBadge from "../../../components/ui/UiBadge.vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiDialogActions from "../../../components/ui/UiDialogActions.vue";
import UiDialog from "../../../components/ui/UiDialog.vue";
import { useMediaQuery } from "../../../composables/media";
import { CLIENT_KEY } from "../../../lib/client";
import { createCompetitionsApi } from "../../../services/competitions";
import { formatEuros } from "../../../lib/format";
import {
  countLine,
  counts,
  COMPETITOR_STATUSES,
  competitorStatusesLabel,
  deadlineOf,
  shownDiscipline,
  disciplineColor,
  filterRows,
  groupRows,
  isArchived,
  isNotInvited,
  memberMatches,
  periodText,
  type Coach,
  type Competition,
  type MemberSlot,
  type Participant,
  type ParticipantFilter,
  type Row,
} from "../competitions";
import CompetitionActions from "./CompetitionActions.vue";
import EmailForm from "./EmailForm.vue";
import EmailHistory from "./EmailHistory.vue";
import { competitorContact, entriesFor, lastSendState } from "./emailHistory";
import { useCompetitionEmailLog } from "./emailLog";
import LastContact from "./LastContact.vue";
import { COMPETITIONS_KEY } from "../context";
import type { QueuedFlag } from "../outbox";
import AthleteContactDialog from "./AthleteContactDialog.vue";
import ParticipantCard from "./ParticipantCard.vue";
import ParticipantRow from "./ParticipantRow.vue";
import PaymentForm from "./PaymentForm.vue";
import WithdrawForm from "./WithdrawForm.vue";
import { competitionItself, WRITER_KEY } from "../writer";
import { formatDateTime, formatDayText } from "../../../lib/format";
import { plural } from "../../../lib/text";
import { dialogs } from "../../../composables/dialogs";

const props = defineProps<{
  competition: Competition;
  rows: readonly Row[];
  members: readonly MemberSlot[];
  coaches: readonly Coach[];
}>();
// Who may write, the outbox and the account: shared by the competitions page with all its sub-pages
const { canWrite, staff, contactsShown, online, outbox, uid } = inject(COMPETITIONS_KEY)!;
const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
const writer = inject(WRITER_KEY)!;

const c = computed(() => props.competition);
const kpis = computed(() => counts(props.rows));
/* Wide screens: the competitors in a table, as on the former desktop page; cards elsewhere */
const wide = useMediaQuery("(min-width: 1280px)");
const filter = ref<ParticipantFilter>("all");
const search = ref("");
const shown = computed(() => filterRows(props.rows, filter.value, search.value));
const groups = computed(() => groupRows(shown.value));
const notInvited = computed(() => props.rows.filter(isNotInvited));
const FILTERS = computed(() => [
  { id: "all" as const, label: "📋 Tous", n: kpis.value.all },
  { id: "selected" as const, label: "✅ Participe : Oui", n: kpis.value.selected },
  { id: "unpaid" as const, label: "⏳ Paiement en attente", n: kpis.value.unpaid },
  ...(canWrite.value ? [{ id: "notInvited" as const, label: "🔘 Non invités", n: notInvited.value.length }] : []),
]);
const server = (r: Row): Participant | undefined => c.value.participants?.find((p) => p.adherent_id === r.adherent_id);
const named = (r: Participant) => `${r.prenom ?? ""} ${r.nom ?? ""}`.trim();

// ---------------------------------------------------------------- The list

const addMemberDialogOpen = ref(false);
const memberSearch = ref("");
const matches = computed(() => memberMatches(props.members, c.value, memberSearch.value));
const statusHint = `Adhérents au statut ${competitorStatusesLabel} uniquement`;
const noMatch = `Aucun adhérent trouvé : seuls les adhérents au statut ${competitorStatusesLabel} peuvent être ajoutés (ou il est déjà inscrit).`;

function openAddMember(): void {
  memberSearch.value = "";
  addMemberDialogOpen.value = true;
}

/** The dialog stays open, search cleared, to add several competitors in a row. */
async function add(m: MemberSlot): Promise<void> {
  const ok = await writer.run(() => competitionsApi.addParticipant(c.value.id, m.id!), {
    competition: competitionItself,
    done: `➕ ${m.prenom} ${m.nom} ajouté(e) à la compétition.`,
  });
  if (ok) {
    memberSearch.value = "";
  }
}

async function loadGroup(): Promise<void> {
  await writer.run(() => competitionsApi.loadGroup(c.value.id, COMPETITOR_STATUSES), {
    competition: (answer) => answer.competition,
    done: (r) =>
      r.added
        ? `🧗 ${r.added} compétiteur(s) du groupe « Compétition » ajouté(s) à la liste.`
        : `ℹ️ Tous les membres ${competitorStatusesLabel} du groupe « Compétition » sont déjà présents dans la liste.`,
  });
}

async function removeNotInvited(): Promise<void> {
  const list = notInvited.value.slice();
  const n = list.length;
  if (
    !n ||
    !(await dialogs.confirm({
      title: "Retirer les non invités",
      message: `Retirer les ${n} compétiteur${plural(n)} non invité${plural(n)} de cette compétition ?\n(Les adhérents restent dans la base du club.)`,
      confirmLabel: "Retirer",
      variant: "danger",
    }))
  ) {
    return;
  }
  let done = 0;
  for (const p of list) {
    const ok = await writer.run(() => competitionsApi.removeParticipant(c.value.id, p.adherent_id!), { competition: competitionItself });
    if (!ok) {
      return;
    }
    done++;
  }
  writer.toast(`🗑 ${done} compétiteur${plural(done)} non invité${plural(done)} retiré${plural(done)}.`);
}

// ---------------------------------------------------------------- One competitor

const withdrawing = ref<Participant | null>(null);
const paying = ref<Participant | null>(null);

/* « Participe » / « Présent ». Unselecting a competitor who paid needs a decision on the money (withdrawal). Offline,
   or when the network drops during the request, the change waits in the outbox. */
async function toggle(r: Row, flag: QueuedFlag, value: boolean): Promise<void> {
  const p = server(r);
  const owner = uid.value;
  if (!p || p.adherent_id == null || !owner) {
    return;
  }
  if (flag === "selectionne" && !value && p.statut_paiement === "paye") {
    withdrawing.value = p;
    return;
  }
  const queue = async () => {
    await outbox.queue(owner, c.value, p, flag, value);
    writer.toast("⏳ Hors ligne : modification gardée sur l'appareil, envoyée au retour du réseau.", 6000);
  };
  if (!writer.online()) {
    return queue();
  }
  if (outbox.pending(c.value.id, p.adherent_id, flag)) {
    await outbox.cancel(c.value.id, p.adherent_id, flag); // superseded by the change sent now
  }
  let lost = false;
  await writer.run(() => competitionsApi.updateParticipant(c.value.id, p.adherent_id!, { [flag]: value }), {
    competition: competitionItself,
    refused: (e) => {
      if (e.code === "already_paid") {
        withdrawing.value = p; // paid meanwhile (HelloAsso): the coach decides what happens to the money
        return true;
      }
      lost = e.status === 0 && e.code === "network";
      return lost;
    },
  });
  if (lost) {
    await queue();
  }
}

async function withdraw(mode: "reporte" | "perdu", note: string): Promise<void> {
  const p = withdrawing.value!;
  const ok = await writer.run(() => competitionsApi.withdraw(c.value.id, p.adherent_id!, { mode, note }), {
    competition: competitionItself,
    done: mode === "reporte" ? `🔄 Désistement de ${named(p)} : paiement reporté.` : `🚫 Désistement de ${named(p)} : paiement perdu.`,
  });
  if (ok) {
    withdrawing.value = null;
  }
}

async function pay(amount: number): Promise<void> {
  const p = paying.value!;
  const ok = await writer.run(() => competitionsApi.payManually(c.value.id, p.adherent_id!, amount), {
    competition: competitionItself,
    done: `✅ Paiement manuel de ${amount} € enregistré pour ${named(p)}.`,
  });
  if (ok) {
    paying.value = null;
  }
}

async function removeOne(r: Row): Promise<void> {
  if (
    !(await dialogs.confirm({
      title: "Supprimer le compétiteur",
      message: `Supprimer ${named(r)} de cette compétition ?\n(L'adhérent reste dans la base du club.)`,
      confirmLabel: "Supprimer",
      variant: "danger",
    }))
  ) {
    return;
  }
  await writer.run(() => competitionsApi.removeParticipant(c.value.id, r.adherent_id!), {
    competition: competitionItself,
    done: `🗑 ${named(r)} supprimé(e) de l'épreuve.`,
  });
}

async function restore(r: Row): Promise<void> {
  if (
    !(await dialogs.confirm({
      title: "Rétablir le compétiteur",
      message: `Rétablir ${named(r)} en compétiteur actif (statut Payé) ?`,
      confirmLabel: "Rétablir",
    }))
  ) {
    return;
  }
  await writer.run(() => competitionsApi.addParticipant(c.value.id, r.adherent_id!), {
    competition: competitionItself,
    done: `✅ ${named(r)} rétabli(e) en compétiteur actif.`,
  });
}

const emailing = ref(false);

// ---------------------------------------------------------------- E-mail history

const emailLog = useCompetitionEmailLog(
  () => c.value.id,
  () => uid.value,
);
const logView = emailLog.view;
/* The history dialog: every send of the competition ("all"), or those that included one competitor */
const historyOf = ref<Row | "all" | null>(null);
const historyOpen = computed({
  get: () => historyOf.value !== null,
  set: (open: boolean) => {
    if (!open) {
      historyOf.value = null;
    }
  },
});
const historyEntries = computed(() => {
  const entries = logView.value.log?.entries ?? [];
  const who = historyOf.value;
  return who === null || who === "all" ? entries : entriesFor(entries, who);
});
const historyTitle = computed(() => {
  const who = historyOf.value;
  return who && who !== "all" ? `✉️ E-mails envoyés à ${named(who)}` : `✉️ E-mails envoyés : ${c.value.nom}`;
});
const contactAthlete = ref<Row | null>(null);
const contactDialogOpen = ref(false);
/* A dialog open while its participant is set; closing it (Escape, outside click) forgets the participant. */
const dialog = (r: { value: Participant | null }) =>
  computed({
    get: () => !!r.value,
    set: (open: boolean) => {
      if (!open) {
        r.value = null;
      }
    },
  });
const withdrawOpen = dialog(withdrawing);
const payingOpen = dialog(paying);

const chip = (active: boolean) => [
  "cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold",
  active ? "border-accent bg-accent text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
];
const field = "rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[13px]";
</script>

<template>
  <!-- Wide screens: the bulk registration block (load the group, remove the never invited) comes before the competitors (flex order), on phones after them -->
  <section data-testid="comp-detail" aria-label="Compétiteurs" :class="wide ? 'flex flex-col' : ''">
    <RouterLink
      :to="{ query: {} }"
      data-testid="back-link"
      class="mb-2 inline-block text-[13px] font-semibold text-accent no-underline md:hidden"
    >
      ‹ Toutes les compétitions
    </RouterLink>
    <div
      class="order-1 mb-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm lg:flex lg:items-start lg:justify-between lg:gap-4 lg:p-4"
    >
      <div class="min-w-0">
        <h2 class="m-0 text-[17px] font-bold lg:text-lg lg:font-extrabold" data-testid="detail-name">{{ c.nom }}</h2>
        <p class="mt-0.5 text-xs text-slate-500 lg:mt-1 lg:text-[12.5px]" data-testid="detail-meta">
          🪪 {{ c.id_ffme || "—" }} · 📅 {{ periodText(c) }}
          <template v-if="deadlineOf(c)">· ⏳ Date limite : {{ formatDayText(deadlineOf(c)) }}</template>
          · 💶 {{ formatEuros(c.prix) }}
          <template v-if="c.lieu">· 📍 {{ c.lieu }}</template>
          <template v-if="isArchived(c)">· 📦 Archivée</template>
          <UiBadge
            v-if="shownDiscipline(c)"
            :color="disciplineColor(shownDiscipline(c))"
            variant="soft"
            class="ml-1"
            data-testid="discipline"
          >
            {{ shownDiscipline(c) }}
          </UiBadge>
        </p>
        <p class="mt-0.5 text-xs text-slate-500 lg:mt-2 lg:flex lg:flex-wrap lg:items-center lg:gap-1.5" data-testid="detail-coaches">
          <template v-if="wide">
            <b class="text-slate-600">🏃 Coachs :</b>
            <UiBadge v-for="name in c.coaches ?? []" :key="name" color="blue" variant="soft">{{ name }}</UiBadge>
            <i v-if="!c.coaches?.length">Aucun coach assigné</i>
          </template>
          <template v-else>🏃 {{ c.coaches?.length ? `Coachs : ${c.coaches.join(", ")}` : "Aucun coach" }}</template>
        </p>
        <p class="mt-0.5 text-xs text-slate-500 lg:mt-1.5" data-testid="detail-last-send">
          ✉️ Dernier envoi aux compétiteurs :
          <LastContact :state="lastSendState(logView)" :online="online" @open="historyOf = 'all'" />
          <span v-if="emailLog.staleSince.value" data-testid="history-stale">
            · 💾 historique du {{ formatDateTime(emailLog.staleSince.value) }}
          </span>
        </p>
        <div class="mt-1.5 flex flex-wrap gap-1.5 lg:mt-2">
          <a
            v-if="c.whatsapp_link"
            :href="c.whatsapp_link"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-2 py-0.5 text-xs font-bold text-green-700 no-underline"
          >
            💬 Groupe WhatsApp ↗
          </a>
          <a
            v-if="c.url_resultats"
            :href="c.url_resultats"
            target="_blank"
            rel="noopener noreferrer"
            data-testid="results-link"
            class="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-bold text-blue-700 no-underline"
          >
            🏆 Résultats MyCompet ↗
          </a>
        </div>
      </div>
      <CompetitionActions
        v-if="canWrite"
        :competition="c"
        :rows="rows"
        :coaches="coaches"
        :not-invited-count="notInvited.length"
        @email="emailing = true"
        @load-group="loadGroup"
        @remove-not-invited="removeNotInvited"
      />
    </div>

    <div :class="wide ? 'order-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm' : ''">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
        <h3 class="text-sm font-bold text-slate-800">Compétiteurs ({{ rows.length }})</h3>
        <div v-if="canWrite" class="flex flex-wrap items-center gap-1.5" data-testid="table-header-actions">
          <UiButton small data-testid="add-competitor-btn" @click="openAddMember">➕ Ajouter un compétiteur</UiButton>
        </div>
      </div>
      <div class="mb-2 flex flex-wrap items-center gap-1.5">
        <input
          v-if="wide"
          v-model="search"
          type="search"
          data-testid="participant-search"
          placeholder="Rechercher un compétiteur…"
          :class="[field, 'w-60']"
        />
        <button
          v-for="f in FILTERS"
          :key="f.id"
          type="button"
          :data-testid="`filter-${f.id}`"
          :aria-pressed="filter === f.id"
          :class="chip(filter === f.id)"
          @click="filter = f.id"
        >
          {{ f.label }} ({{ f.n }})
        </button>
        <input
          v-if="!wide"
          v-model="search"
          type="search"
          data-testid="participant-search"
          placeholder="Rechercher un compétiteur…"
          :class="[field, 'min-w-40 flex-1']"
        />
      </div>
      <p class="mb-2 text-xs text-slate-500" data-testid="participant-count">{{ countLine(kpis, filter, shown.length) }}</p>

      <details
        v-if="canWrite"
        class="mb-3 rounded-lg border border-slate-200 bg-slate-50 text-xs leading-relaxed"
        data-testid="actions-guide"
      >
        <summary class="cursor-pointer px-3.5 py-2 font-bold text-slate-800 select-none">
          ℹ️ Guide des actions sur les compétiteurs (quand les utiliser et conséquences)
        </summary>
        <div class="grid gap-2.5 px-3.5 pb-3 lg:grid-cols-3">
          <div class="rounded-md border border-l-[3px] border-blue-200 border-l-blue-600 bg-white px-2.5 py-2">
            <b class="text-blue-700">1. ☑️ Participe (sélection, convocation)</b>
            <div class="mt-0.5 text-slate-600">
              <b>Quand :</b>
              pour convoquer un athlète à l'épreuve, en composant l'équipe.
              <br />
              <b>Conséquences :</b>
              l'athlète entre dans le quota des inscrits, passe en
              <i>En attente</i>
              de règlement HelloAsso, reçoit les e-mails de convocation et le tarif de l'épreuve s'ajoute à son dû dans la balance
              financière.
            </div>
          </div>
          <div class="rounded-md border border-l-[3px] border-green-200 border-l-green-600 bg-white px-2.5 py-2">
            <b class="text-green-700">2. ☑️ Présent (pointage le jour J)</b>
            <div class="mt-0.5 text-slate-600">
              <b>Quand :</b>
              sur place, le jour de la compétition, à l'arrivée de l'athlète.
              <br />
              <b>Conséquences :</b>
              valide sa présence.
              <b>Une fois pointé présent, le retrait et le désistement sont verrouillés</b>
              (badge
              <i>✓ Sur place</i>
              ) ; décochez la case après une erreur de pointage pour les retrouver.
            </div>
          </div>
          <div class="rounded-md border border-l-[3px] border-red-200 border-l-red-600 bg-white px-2.5 py-2">
            <b class="text-red-700">3. ✕ Retirer de l'épreuve</b>
            <div class="mt-0.5 text-slate-600">
              <b>Quand :</b>
              athlète ajouté par erreur, ou nettoyage des non-invités.
              <br />
              <b>Conséquences :</b>
              supprime sa ligne de cette compétition (« Retirer tous les compétiteurs non invités » nettoie la liste en un clic).
              <br />
              <i>
                ⚠️ Un athlète qui a payé ne peut pas être retiré : « 🔒 Désister… » le passe en « Annulé — report » ou « Annulé — perdu »,
                la trace comptable est conservée.
              </i>
            </div>
          </div>
        </div>
      </details>

      <p v-if="!groups.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">
        {{ rows.length ? "Aucun compétiteur ne correspond au filtre." : "Aucun compétiteur inscrit." }}
      </p>
      <div v-if="wide && groups.length" class="overflow-x-auto rounded-lg border border-slate-200">
        <table class="w-full border-collapse text-left text-[13px]" aria-label="Compétiteurs">
          <thead class="bg-slate-50 text-[11px] font-bold whitespace-nowrap text-slate-500 uppercase">
            <tr>
              <th class="px-2.5 py-2">Athlète</th>
              <th class="px-2.5 py-2 text-center">Résultat</th>
              <th class="px-2.5 py-2 text-center" title="Sélection de l'athlète : sa convocation, et le suivi de son paiement">
                Participe
              </th>
              <th class="px-2.5 py-2">Paiement</th>
              <th class="px-2.5 py-2">Contact</th>
              <th v-if="canWrite" class="px-2.5 py-2 text-center">Action</th>
            </tr>
          </thead>
          <tbody v-for="[group, list] in groups" :key="group" data-testid="participant-group">
            <tr class="border-t border-slate-200 bg-slate-100/70">
              <th :colspan="canWrite ? 6 : 5" class="px-2.5 py-1.5 text-xs font-bold text-slate-600 uppercase">
                {{ group }} · {{ list.length }} compétiteur{{ plural(list.length) }}
              </th>
            </tr>
            <ParticipantRow
              v-for="r in list"
              :key="r.adherent_id ?? `${r.nom}-${r.prenom}`"
              :row="r"
              :contact="competitorContact(logView, r)"
              :online="online"
              :can-write="canWrite"
              :staff="staff || canWrite"
              :contacts-shown="contactsShown"
              @history="historyOf = r"
              @toggle="(flag, value) => toggle(r, flag, value)"
              @remove="removeOne(r)"
              @pay="paying = server(r) ?? null"
              @withdraw="withdrawing = server(r) ?? null"
              @restore="restore(r)"
              @show-contact="
                contactAthlete = r;
                contactDialogOpen = true;
              "
            />
          </tbody>
        </table>
      </div>
      <template v-else>
        <div v-for="[group, list] in groups" :key="group" class="mb-3" data-testid="participant-group">
          <h3 class="mb-1.5 text-xs font-bold text-slate-600 uppercase">
            {{ group }} · {{ list.length }} compétiteur{{ plural(list.length) }}
          </h3>
          <ul class="grid gap-2 xl:grid-cols-2">
            <ParticipantCard
              v-for="r in list"
              :key="r.adherent_id ?? `${r.nom}-${r.prenom}`"
              :row="r"
              :contact="competitorContact(logView, r)"
              :online="online"
              :can-write="canWrite"
              :staff="staff || canWrite"
              :contacts-shown="contactsShown"
              @history="historyOf = r"
              @toggle="(flag, value) => toggle(r, flag, value)"
              @remove="removeOne(r)"
              @pay="paying = server(r) ?? null"
              @withdraw="withdrawing = server(r) ?? null"
              @restore="restore(r)"
              @show-contact="
                contactAthlete = r;
                contactDialogOpen = true;
              "
            />
          </ul>
        </div>
      </template>
    </div>

    <UiDialog v-model:open="withdrawOpen" title="⚠️ Désistement d'un compétiteur qui a payé" data-testid="withdraw-dialog">
      <WithdrawForm
        v-if="withdrawing"
        :participant="withdrawing"
        :busy="writer.busy.value"
        @confirm="withdraw"
        @cancel="withdrawing = null"
      />
    </UiDialog>
    <UiDialog v-model:open="payingOpen" title="💶 Paiement manuel" data-testid="payment-dialog">
      <PaymentForm
        v-if="paying"
        :participant="paying"
        :price="Number(c.prix ?? 0)"
        :busy="writer.busy.value"
        @confirm="pay"
        @cancel="paying = null"
      />
    </UiDialog>
    <UiDialog v-model:open="emailing" :title="`✉️ E-mail aux compétiteurs : ${c.nom}`" wide data-testid="email-dialog">
      <EmailForm
        v-if="emailing"
        :competition="c"
        :rows="rows"
        @sent="
          (m) => {
            emailing = false;
            writer.toast(m, 6000);
            void emailLog.refresh();
          }
        "
        @cancel="emailing = false"
      />
    </UiDialog>

    <UiDialog v-model:open="historyOpen" :title="historyTitle" wide data-testid="history-dialog">
      <p v-if="emailLog.staleSince.value" class="mb-2 text-xs text-amber-800">
        💾 Historique du {{ formatDateTime(emailLog.staleSince.value) }} : les envois suivants n'y figurent pas.
      </p>
      <EmailHistory :entries="historyEntries" />
    </UiDialog>

    <!-- Wide: long tariff names (« Compétition U15 U17 - nés en 2008, … ») stay on one line on a computer -->
    <UiDialog v-model:open="addMemberDialogOpen" title="➕ Ajouter un compétiteur" wide data-testid="add-competitor-dialog">
      <div class="flex flex-col gap-3">
        <p class="text-xs text-slate-600">
          Recherchez un adhérent du club par son nom, prénom ou numéro de licence pour l'inscrire à cette compétition.
        </p>
        <input
          v-model="memberSearch"
          type="search"
          data-testid="member-search"
          placeholder="Nom, prénom ou licence (2 lettres au moins)…"
          :class="field"
        />
        <p class="-mt-2 text-xs text-slate-500" data-testid="member-status-hint">{{ statusHint }}</p>
        <ul class="max-h-60 overflow-y-auto flex flex-col divide-y divide-slate-100">
          <li v-for="m in matches" :key="m.id!" data-testid="member-result" class="flex items-center justify-between gap-2 py-2">
            <span class="min-w-0 flex-1">
              <b class="text-[13px] text-slate-800">{{ m.nom }} {{ m.prenom }}</b>
              <span class="block text-xs text-slate-500">🪪 {{ m.licence_ffme || "sans licence" }} · {{ m.tarif || "—" }}</span>
            </span>
            <!-- Same size on every row, however long the tariff next to it -->
            <UiButton small class="shrink-0 whitespace-nowrap" data-testid="member-add" :disabled="writer.busy.value" @click="add(m)">
              ➕ Inscrire
            </UiButton>
          </li>
          <li v-if="memberSearch.trim().length >= 2 && !matches.length" class="text-xs text-slate-500 py-4 text-center">
            {{ members.length ? noMatch : "Annuaire des adhérents indisponible (réseau ?)." }}
          </li>
        </ul>
        <UiDialogActions>
          <UiButton variant="muted" @click="addMemberDialogOpen = false">Fermer</UiButton>
        </UiDialogActions>
      </div>
    </UiDialog>

    <AthleteContactDialog v-model:open="contactDialogOpen" :athlete="contactAthlete" />
  </section>
</template>
