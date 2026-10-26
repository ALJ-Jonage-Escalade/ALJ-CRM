<script setup lang="ts">
/* One competition: its details, counters and competitors by slot group (a table on wide screens, cards elsewhere). Coaches and admins change it here (plan phase
   11): the competition itself (edit, archive, delete), its list (add a member, load the competition group, remove the
   ones never invited), each competitor (ParticipantCard), its MyCompet results, an e-mail to its competitors and a
   spreadsheet export. « Participe » and « Présent » also change offline (the outbox, sent when the network comes back). */
import { computed, inject, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import UiBadge from "../../components/ui/UiBadge.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import UiMenu from "../../components/ui/UiMenu.vue";
import UiMenuItem from "../../components/ui/UiMenuItem.vue";
import { useMediaQuery } from "../../composables/media";
import { CLIENT_KEY, type Schemas } from "../../lib/client";
import { createCompetitionsApi } from "../../services/competitions";
import { csvBlob } from "../../lib/csv";
import { saveFile } from "../../lib/download";
import { formatEuros } from "../../lib/format";
import CompetitionForm from "./CompetitionForm.vue";
import {
  countLine,
  counts,
  csvName,
  discipline,
  disciplineColor,
  filterRows,
  groupRows,
  isArchived,
  isNotInvited,
  memberMatches,
  participantCsv,
  period,
  resultsUrlHint,
  type Coach,
  type Competition,
  type MemberSlot,
  type Participant,
  type ParticipantFilter,
  type Row,
} from "./competitions";
import EmailForm from "./EmailForm.vue";
import type { Outbox, QueuedFlag } from "./outbox";
import ParticipantCard from "./ParticipantCard.vue";
import ParticipantRow from "./ParticipantRow.vue";
import PaymentForm from "./PaymentForm.vue";
import WithdrawForm from "./WithdrawForm.vue";
import { WRITER_KEY } from "./writer";
import { plural } from "../../lib/text";
import { dialogs } from "../../composables/dialogs";

const props = defineProps<{
  competition: Competition;
  rows: readonly Row[];
  members: readonly MemberSlot[];
  coaches: readonly Coach[];
  /** Coaches and admins (offline: a device that keeps the contacts, i.e. a coach's) */
  canWrite: boolean;
  staff: boolean;
  contactsShown: boolean;
  outbox: Outbox;
  uid: string | null;
}>();
const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
const writer = inject(WRITER_KEY)!;
const router = useRouter();

const c = computed(() => props.competition);
const kpis = computed(() => counts(props.rows));
const KPIS = computed(() => [
  { id: "selected", label: "Participe", value: String(kpis.value.selected), color: "text-blue-600" },
  { id: "unpaid", label: "Paiement en attente", value: String(kpis.value.unpaid), color: "text-amber-600" },
  { id: "paid", label: "Paiement validé", value: String(kpis.value.paid), color: "text-green-600" },
  { id: "present", label: "Présents", value: `${kpis.value.present} / ${kpis.value.selected}`, color: "text-violet-600" },
]);
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
  ...(props.canWrite ? [{ id: "notInvited" as const, label: "🔘 Non invités", n: notInvited.value.length }] : []),
]);
const server = (r: Row): Participant | undefined => c.value.participants?.find((p) => p.adherent_id === r.adherent_id);
const named = (r: Participant) => `${r.prenom ?? ""} ${r.nom ?? ""}`.trim();

// ---------------------------------------------------------------- The competition

const editing = ref(false);

async function save(body: Schemas["CompetitionCreate"]): Promise<void> {
  if (
    await writer.run(() => competitionsApi.update(c.value.id, body), {
      done: "✅ Compétition mise à jour.",
    })
  ) {
    editing.value = false;
  }
}

async function remove(): Promise<void> {
  if (
    !(await dialogs.confirm({
      title: "Supprimer la compétition",
      message: `Supprimer définitivement « ${c.value.nom} » et sa liste de compétiteurs ?`,
      confirmLabel: "Supprimer",
      variant: "danger",
    }))
  ) {
    return;
  }
  const id = c.value.id;
  if (
    await writer.run(() => competitionsApi.remove(id), {
      done: "🗑 Compétition supprimée.",
    })
  ) {
    editing.value = false;
    writer.dropped(id);
    await router.push({ query: {} });
  }
}

async function archive(archived: boolean): Promise<void> {
  const nom = c.value.nom;
  await writer.run(() => competitionsApi.setArchived(c.value.id, archived), {
    done: archived ? `📦 « ${nom} » archivée.` : `♻️ « ${nom} » désarchivée.`,
  });
}

function exportCsv(): void {
  saveFile(csvBlob(participantCsv(props.rows)), csvName(c.value));
}

// ---------------------------------------------------------------- MyCompet results

const fetching = ref(false);
const askUrl = ref(false);
const resultsUrl = ref("");

async function fetchResults(url = ""): Promise<void> {
  fetching.value = true;
  askUrl.value = false;
  writer.toast(
    url || c.value.url_resultats
      ? `⏳ Recherche des résultats de « ${c.value.nom} »…`
      : `🔍 Recherche automatique des résultats MyCompet de « ${c.value.nom} »…`,
    6000,
  );
  try {
    await writer.run(() => competitionsApi.fetchResults(c.value.id, url), {
      done: (r) => `🏆 ${r.matched_count} résultat(s) associé(s) sur ${r.total_scraped} compétiteur(s) ALJ trouvé(s).`,
      refused: (e) => {
        if (e.code !== "needs_url") {
          return false;
        }
        resultsUrl.value = "";
        askUrl.value = true; // not found on MyCompet: the coach gives the page
        return true;
      },
    });
  } finally {
    fetching.value = false;
  }
}

// ---------------------------------------------------------------- The list

const adding = ref(false);
const memberSearch = ref("");
const matches = computed(() => memberMatches(props.members, c.value, memberSearch.value));

async function add(m: MemberSlot): Promise<void> {
  await writer.run(() => competitionsApi.addParticipant(c.value.id, m.id!), {
    done: `➕ ${m.prenom} ${m.nom} ajouté(e) à la compétition.`,
  });
}

async function loadGroup(): Promise<void> {
  await writer.run(() => competitionsApi.loadGroup(c.value.id), {
    done: (r) =>
      r.added
        ? `🧗 ${r.added} compétiteur(s) du groupe « Compétition » ajouté(s) à la liste.`
        : "ℹ️ Tous les membres du groupe « Compétition » sont déjà présents dans la liste.",
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
    const ok = await writer.run(() => competitionsApi.removeParticipant(c.value.id, p.adherent_id!));
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
  if (!p || p.adherent_id == null || !props.uid) {
    return;
  }
  if (flag === "selectionne" && !value && p.statut_paiement === "paye") {
    withdrawing.value = p;
    return;
  }
  const queue = async () => {
    await props.outbox.queue(props.uid!, c.value, p, flag, value);
    writer.toast("⏳ Hors ligne : modification gardée sur l'appareil, envoyée au retour du réseau.", 6000);
  };
  if (!writer.online()) {
    return queue();
  }
  if (props.outbox.pending(c.value.id, p.adherent_id, flag)) {
    await props.outbox.queue(props.uid, c.value, p, flag, !!p[flag]);
  } // superseded
  let lost = false;
  await writer.run(() => competitionsApi.updateParticipant(c.value.id, p.adherent_id!, { [flag]: value }), {
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
    done: mode === "reporte" ? `🔄 Désistement de ${named(p)} : paiement reporté.` : `🚫 Désistement de ${named(p)} : paiement perdu.`,
  });
  if (ok) {
    withdrawing.value = null;
  }
}

async function pay(amount: number): Promise<void> {
  const p = paying.value!;
  const ok = await writer.run(() => competitionsApi.payManually(c.value.id, p.adherent_id!, amount), {
    done: `✅ Paiement manuel de ${amount} € enregistré pour ${named(p)}.`,
  });
  if (ok) {
    paying.value = null;
  }
}

async function removeOne(r: Row): Promise<void> {
  if (
    !(await dialogs.confirm({
      title: "Retirer le compétiteur",
      message: `Retirer ${named(r)} de cette compétition ?\n(L'adhérent reste dans la base du club.)`,
      confirmLabel: "Retirer",
      variant: "danger",
    }))
  ) {
    return;
  }
  await writer.run(() => competitionsApi.removeParticipant(c.value.id, r.adherent_id!), {
    done: `🗑 ${named(r)} retiré(e) de l'épreuve.`,
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
    done: `✅ ${named(r)} rétabli(e) en compétiteur actif.`,
  });
}

const emailing = ref(false);
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
  <!-- Wide screens: the block adding members comes before the competitors (flex order), on phones after them -->
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
          🪪 {{ c.id_ffme || "—" }} · 📅 {{ period(c) }} · 💶 {{ formatEuros(c.prix) }}
          <template v-if="c.lieu">· 📍 {{ c.lieu }}</template>
          <template v-if="isArchived(c)">· 📦 Archivée</template>
          <UiBadge v-if="discipline(c)" :color="disciplineColor(discipline(c))" variant="soft" class="ml-1" data-testid="discipline">
            {{ discipline(c) }}
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
      <div
        v-if="canWrite"
        class="mt-2.5 flex flex-wrap gap-1.5 lg:mt-0 lg:max-w-[45%] lg:shrink-0 lg:justify-end"
        data-testid="detail-actions"
      >
        <UiButton variant="muted" small data-testid="edit-comp" @click="editing = true">✏️ Modifier</UiButton>
        <UiButton variant="muted" small data-testid="email-comp" @click="emailing = true">✉️ E-mail aux compétiteurs</UiButton>
        <!-- The actions rarely needed (the results are also fetched every night) -->
        <UiMenu label="⋯ Plus" small :busy="fetching && 'Recherche MyCompet…'" aria-label="Plus d'actions" data-testid="detail-more">
          <UiMenuItem data-testid="fetch-results" @select="fetchResults()">🏆 Trouver les résultats</UiMenuItem>
          <UiMenuItem data-testid="export-csv" :disabled="!rows.length" @select="exportCsv">📥 Export CSV</UiMenuItem>
          <UiMenuItem :data-testid="isArchived(c) ? 'unarchive-comp' : 'archive-comp'" @select="archive(!isArchived(c))">
            {{ isArchived(c) ? "♻️ Désarchiver" : "📦 Archiver" }}
          </UiMenuItem>
          <UiMenuItem danger data-testid="delete-comp" :disabled="writer.busy.value" @select="remove">🗑️ Supprimer</UiMenuItem>
        </UiMenu>
      </div>
    </div>

    <div class="order-1 mb-3 grid grid-cols-4 gap-2 text-center lg:gap-2.5">
      <div v-for="k in KPIS" :key="k.id" class="rounded-xl border border-slate-200 bg-white px-1 py-2 shadow-sm lg:px-3 lg:py-2.5">
        <div :class="['text-xl font-extrabold', k.color]" :data-testid="`kpi-${k.id}`">{{ k.value }}</div>
        <div class="text-[11px] font-semibold text-slate-500 lg:uppercase">{{ k.label }}</div>
      </div>
    </div>

    <div :class="wide ? 'order-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm' : ''">
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
              <th class="px-2.5 py-2 text-center" title="Pointage sur place le jour de l'épreuve">Présent</th>
              <th class="px-2.5 py-2">Contact</th>
              <th v-if="canWrite" class="px-2.5 py-2 text-center">Action</th>
            </tr>
          </thead>
          <tbody v-for="[group, list] in groups" :key="group" data-testid="participant-group">
            <tr class="border-t border-slate-200 bg-slate-100/70">
              <th :colspan="canWrite ? 7 : 6" class="px-2.5 py-1.5 text-xs font-bold text-slate-600 uppercase">
                {{ group }} · {{ list.length }} compétiteur{{ plural(list.length) }}
              </th>
            </tr>
            <ParticipantRow
              v-for="r in list"
              :key="r.adherent_id ?? `${r.nom}-${r.prenom}`"
              :row="r"
              :can-write="canWrite"
              :staff="staff || canWrite"
              :contacts-shown="contactsShown"
              @toggle="(flag, value) => toggle(r, flag, value)"
              @remove="removeOne(r)"
              @pay="paying = server(r) ?? null"
              @withdraw="withdrawing = server(r) ?? null"
              @restore="restore(r)"
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
              :can-write="canWrite"
              :staff="staff || canWrite"
              :contacts-shown="contactsShown"
              @toggle="(flag, value) => toggle(r, flag, value)"
              @remove="removeOne(r)"
              @pay="paying = server(r) ?? null"
              @withdraw="withdrawing = server(r) ?? null"
              @restore="restore(r)"
            />
          </ul>
        </div>
      </template>
    </div>

    <div
      v-if="canWrite"
      :class="['rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm', wide ? 'order-2 mb-3' : 'mt-4']"
      data-testid="add-members"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <b class="text-[13.5px]">Gérer les inscriptions</b>
        <div class="flex flex-wrap gap-2">
          <UiButton variant="muted" small data-testid="toggle-add" :aria-expanded="adding" @click="adding = !adding">
            {{ adding ? "Fermer" : "🔍 Rechercher un adhérent" }}
          </UiButton>
          <UiButton variant="muted" small data-testid="load-group" @click="loadGroup">🧗 Charger le groupe « Compétition »</UiButton>
          <UiButton
            v-if="canWrite"
            variant="danger"
            small
            data-testid="remove-not-invited"
            :disabled="!notInvited.length || writer.busy.value"
            title="Retirer de cette compétition tous les athlètes jamais invités (ils restent dans la base du club)"
            @click="removeNotInvited"
          >
            🗑️ Retirer tous les compétiteurs non invités ({{ notInvited.length }})
          </UiButton>
        </div>
      </div>
      <template v-if="adding">
        <input
          v-model="memberSearch"
          type="search"
          data-testid="member-search"
          placeholder="Nom, prénom ou licence (2 lettres au moins)"
          :class="[field, 'mt-2 w-full']"
        />
        <ul class="mt-2 flex flex-col">
          <li
            v-for="m in matches"
            :key="m.id!"
            data-testid="member-result"
            class="flex items-center justify-between gap-2 border-b border-slate-100 py-1.5"
          >
            <span class="min-w-0">
              <b class="text-[13px]">{{ m.nom }} {{ m.prenom }}</b>
              <span class="block text-xs text-slate-500">🪪 {{ m.licence_ffme || "sans licence" }} · {{ m.tarif || "—" }}</span>
            </span>
            <UiButton small data-testid="member-add" :disabled="writer.busy.value" @click="add(m)">➕ Ajouter</UiButton>
          </li>
          <li v-if="memberSearch.trim().length >= 2 && !matches.length" class="text-xs text-slate-500">
            {{ members.length ? "Aucun adhérent trouvé (ou déjà inscrit)." : "Annuaire des adhérents indisponible (réseau ?)." }}
          </li>
        </ul>
      </template>
    </div>

    <UiDialog v-model:open="editing" :title="`✏️ Modifier : ${c.nom}`" wide data-testid="edit-dialog">
      <CompetitionForm
        v-if="editing"
        :competition="c"
        :coaches="coaches"
        :busy="writer.busy.value"
        @save="save"
        @cancel="editing = false"
      />
    </UiDialog>
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
    <UiDialog v-model:open="askUrl" title="🏆 Résultats introuvables sur MyCompet" data-testid="results-dialog">
      <form class="flex flex-col gap-3" @submit.prevent="resultsUrl.trim() && fetchResults(resultsUrl.trim())">
        <p class="text-[13px]">
          Si les résultats de « {{ c.nom }} » sont publiés, donnez l'adresse ou le numéro de leur page ({{ resultsUrlHint }}).
        </p>
        <input v-model="resultsUrl" data-testid="results-url" :class="field" :placeholder="resultsUrlHint" />
        <UiDialogActions>
          <UiButton variant="muted" @click="askUrl = false">Annuler</UiButton>
          <UiButton type="submit" data-testid="results-ok" :disabled="!resultsUrl.trim()">🔍 Chercher</UiButton>
        </UiDialogActions>
      </form>
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
          }
        "
        @cancel="emailing = false"
      />
    </UiDialog>
  </section>
</template>
