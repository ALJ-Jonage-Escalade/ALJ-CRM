<script setup lang="ts">
/* One competition: its details, counters and competitors by slot group. Coaches and admins change it here (plan phase
   11): the competition itself (edit, archive, delete), its list (add a member, load the competition group, remove the
   ones never invited), each competitor (ParticipantCard), its MyCompet results, an e-mail to its competitors and a
   spreadsheet export. « Participe » and « Présent » also change offline (the outbox, sent when the network comes back). */
import { computed, inject, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import { CLIENT_KEY, unwrap, type Schemas } from "../../lib/client";
import { csvBlob } from "../../lib/csv";
import { saveFile } from "../../lib/download";
import CompetitionForm from "./CompetitionForm.vue";
import {
  countLine,
  counts,
  csvName,
  discipline,
  euros,
  filterRows,
  groupRows,
  isArchived,
  isNotInvited,
  memberMatches,
  participantCsv,
  PREPARING,
  ARCHIVED,
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
import PaymentForm from "./PaymentForm.vue";
import WithdrawForm from "./WithdrawForm.vue";
import { WRITER_KEY } from "./writer";

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
const client = inject(CLIENT_KEY)!;
const writer = inject(WRITER_KEY)!;
const router = useRouter();

const c = computed(() => props.competition);
const path = computed(() => ({ competition_id: c.value.id }));
const kpis = computed(() => counts(props.rows));
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
const plural = (n: number) => (n > 1 ? "s" : "");
const server = (r: Row): Participant | undefined => c.value.participants?.find((p) => p.adherent_id === r.adherent_id);
const named = (r: Participant) => `${r.prenom ?? ""} ${r.nom ?? ""}`.trim();

// ---------------------------------------------------------------- The competition

const editing = ref(false);

async function save(body: Schemas["CompetitionCreate"]): Promise<void> {
  if (
    await writer.run(() => unwrap(client.PATCH("/api/competitions/{competition_id}", { params: { path: path.value }, body })), {
      done: "✅ Compétition mise à jour.",
    })
  ) {
    editing.value = false;
  }
}

async function remove(): Promise<void> {
  if (!confirm(`Supprimer définitivement « ${c.value.nom} » et sa liste de compétiteurs ?`)) {
    return;
  }
  const id = c.value.id;
  if (
    await writer.run(() => unwrap(client.DELETE("/api/competitions/{competition_id}", { params: { path: path.value } })), {
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
  await writer.run(
    () =>
      unwrap(
        client.PATCH("/api/competitions/{competition_id}", {
          params: { path: path.value },
          body: { statut: archived ? ARCHIVED : PREPARING },
        }),
      ),
    {
      done: archived ? `📦 « ${nom} » archivée.` : `♻️ « ${nom} » désarchivée.`,
    },
  );
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
    await writer.run(
      () =>
        unwrap(
          client.POST("/api/competitions/{comp_id}/fetch-results", {
            params: { path: { comp_id: String(c.value.id) } },
            body: { url, club: "JONAGE" },
          }),
        ),
      {
        done: (r) => `🏆 ${r.matched_count} résultat(s) associé(s) sur ${r.total_scraped} compétiteur(s) ALJ trouvé(s).`,
        refused: (e) => {
          if (e.code !== "needs_url") {
            return false;
          }
          resultsUrl.value = "";
          askUrl.value = true; // not found on MyCompet: the coach gives the page
          return true;
        },
      },
    );
  } finally {
    fetching.value = false;
  }
}

// ---------------------------------------------------------------- The list

const adding = ref(false);
const memberSearch = ref("");
const matches = computed(() => memberMatches(props.members, c.value, memberSearch.value));

async function add(m: MemberSlot): Promise<void> {
  await writer.run(
    () =>
      unwrap(
        client.POST("/api/competitions/{competition_id}/participants", {
          params: { path: path.value },
          body: { adherent_id: m.id!, selectionne: true },
        }),
      ),
    {
      done: `➕ ${m.prenom} ${m.nom} ajouté(e) à la compétition.`,
    },
  );
}

async function loadGroup(): Promise<void> {
  await writer.run(() => unwrap(client.POST("/api/competitions/{competition_id}/load-group", { params: { path: path.value } })), {
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
    !confirm(
      `Retirer les ${n} compétiteur${plural(n)} non invité${plural(n)} de cette compétition ?\n(Les adhérents restent dans la base du club.)`,
    )
  ) {
    return;
  }
  let done = 0;
  for (const p of list) {
    const ok = await writer.run(() =>
      unwrap(
        client.DELETE("/api/competitions/{competition_id}/participants/{adherent_id}", {
          params: { path: { ...path.value, adherent_id: p.adherent_id! } },
        }),
      ),
    );
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
const participantPath = (p: Participant) => ({ params: { path: { ...path.value, adherent_id: p.adherent_id! } } });

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
  await writer.run(
    () =>
      unwrap(
        client.PATCH("/api/competitions/{competition_id}/participants/{adherent_id}", { ...participantPath(p), body: { [flag]: value } }),
      ),
    {
      refused: (e) => {
        if (e.code === "already_paid") {
          withdrawing.value = p; // paid meanwhile (HelloAsso): the coach decides what happens to the money
          return true;
        }
        lost = e.status === 0 && e.code === "network";
        return lost;
      },
    },
  );
  if (lost) {
    await queue();
  }
}

async function withdraw(mode: "reporte" | "perdu", note: string): Promise<void> {
  const p = withdrawing.value!;
  const ok = await writer.run(
    () =>
      unwrap(
        client.POST("/api/competitions/{competition_id}/participants/{adherent_id}/cancel", {
          ...participantPath(p),
          body: { mode, note },
        }),
      ),
    {
      done: mode === "reporte" ? `🔄 Désistement de ${named(p)} : paiement reporté.` : `🚫 Désistement de ${named(p)} : paiement perdu.`,
    },
  );
  if (ok) {
    withdrawing.value = null;
  }
}

async function pay(amount: number): Promise<void> {
  const p = paying.value!;
  const ok = await writer.run(
    () =>
      unwrap(
        client.POST("/api/competitions/{competition_id}/participants/{adherent_id}/manual-payment", {
          ...participantPath(p),
          body: { montant: amount },
        }),
      ),
    {
      done: `✅ Paiement manuel de ${amount} € enregistré pour ${named(p)}.`,
    },
  );
  if (ok) {
    paying.value = null;
  }
}

async function removeOne(r: Row): Promise<void> {
  if (!confirm(`Retirer ${named(r)} de cette compétition ?\n(L'adhérent reste dans la base du club.)`)) {
    return;
  }
  await writer.run(() => unwrap(client.DELETE("/api/competitions/{competition_id}/participants/{adherent_id}", participantPath(r))), {
    done: `🗑 ${named(r)} retiré(e) de l'épreuve.`,
  });
}

async function restore(r: Row): Promise<void> {
  if (!confirm(`Rétablir ${named(r)} en compétiteur actif (statut Payé) ?`)) {
    return;
  }
  await writer.run(
    () =>
      unwrap(
        client.POST("/api/competitions/{competition_id}/participants", {
          params: { path: path.value },
          body: { adherent_id: r.adherent_id!, selectionne: true },
        }),
      ),
    {
      done: `✅ ${named(r)} rétabli(e) en compétiteur actif.`,
    },
  );
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
  <section data-testid="comp-detail" aria-label="Compétiteurs">
    <RouterLink
      :to="{ query: {} }"
      data-testid="back-link"
      class="mb-2 inline-block text-[13px] font-semibold text-accent no-underline md:hidden"
      >‹ Toutes les compétitions</RouterLink
    >
    <div class="mb-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <h2 class="m-0 text-[17px] font-bold" data-testid="detail-name">{{ c.nom }}</h2>
      <p class="mt-0.5 text-xs text-slate-500" data-testid="detail-meta">
        🪪 {{ c.id_ffme || "—" }} · 📅 {{ period(c) }} · 💶 {{ euros(c.prix) }}<template v-if="c.lieu"> · 📍 {{ c.lieu }}</template
        ><template v-if="discipline(c)"> · {{ discipline(c) }}</template
        ><template v-if="isArchived(c)"> · 📦 Archivée</template>
      </p>
      <p class="mt-0.5 text-xs text-slate-500" data-testid="detail-coaches">
        🏃 {{ c.coaches?.length ? `Coachs : ${c.coaches.join(", ")}` : "Aucun coach" }}
      </p>
      <div class="mt-1.5 flex flex-wrap gap-1.5">
        <a
          v-if="c.whatsapp_link"
          :href="c.whatsapp_link"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-2 py-0.5 text-xs font-bold text-green-700 no-underline"
          >💬 Groupe WhatsApp ↗</a
        >
        <a
          v-if="c.url_resultats"
          :href="c.url_resultats"
          target="_blank"
          rel="noopener noreferrer"
          data-testid="results-link"
          class="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-bold text-blue-700 no-underline"
          >🏆 Résultats MyCompet ↗</a
        >
      </div>
      <div v-if="canWrite" class="mt-2.5 flex flex-wrap gap-1.5" data-testid="detail-actions">
        <UiButton variant="muted" small data-testid="edit-comp" @click="editing = true">✏️ Modifier</UiButton>
        <UiButton variant="muted" small :data-testid="isArchived(c) ? 'unarchive-comp' : 'archive-comp'" @click="archive(!isArchived(c))">{{
          isArchived(c) ? "♻️ Désarchiver" : "📦 Archiver"
        }}</UiButton>
        <UiButton variant="muted" small data-testid="fetch-results" :busy="fetching && 'Recherche MyCompet…'" @click="fetchResults()"
          >🏆 Trouver les résultats</UiButton
        >
        <UiButton variant="muted" small data-testid="email-comp" @click="emailing = true">✉️ E-mail aux compétiteurs</UiButton>
        <UiButton variant="muted" small data-testid="export-csv" :disabled="!rows.length" @click="exportCsv">📥 Export CSV</UiButton>
      </div>
      <div class="mt-3 grid grid-cols-4 gap-2 text-center">
        <div>
          <div class="text-xl font-extrabold text-blue-600" data-testid="kpi-selected">{{ kpis.selected }}</div>
          <div class="text-[11px] font-semibold text-slate-500">Participe</div>
        </div>
        <div>
          <div class="text-xl font-extrabold text-amber-600" data-testid="kpi-unpaid">{{ kpis.unpaid }}</div>
          <div class="text-[11px] font-semibold text-slate-500">Paiement en attente</div>
        </div>
        <div>
          <div class="text-xl font-extrabold text-green-600" data-testid="kpi-paid">{{ kpis.paid }}</div>
          <div class="text-[11px] font-semibold text-slate-500">Paiement validé</div>
        </div>
        <div>
          <div class="text-xl font-extrabold text-violet-600" data-testid="kpi-present">{{ kpis.present }} / {{ kpis.selected }}</div>
          <div class="text-[11px] font-semibold text-slate-500">Présents</div>
        </div>
      </div>
    </div>

    <div class="mb-2 flex flex-wrap items-center gap-1.5">
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
        v-model="search"
        type="search"
        data-testid="participant-search"
        placeholder="Rechercher un compétiteur…"
        :class="[field, 'min-w-40 flex-1']"
      />
    </div>
    <div class="mb-2 flex flex-wrap items-center gap-2">
      <p class="m-0 text-xs text-slate-500" data-testid="participant-count">{{ countLine(kpis, filter, shown.length) }}</p>
      <UiButton
        v-if="canWrite && filter === 'notInvited' && notInvited.length"
        variant="danger"
        small
        class="ml-auto"
        data-testid="remove-not-invited"
        @click="removeNotInvited"
      >
        🗑 Retirer les {{ notInvited.length }} non invité{{ plural(notInvited.length) }}
      </UiButton>
    </div>

    <p v-if="!groups.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">
      {{ rows.length ? "Aucun compétiteur ne correspond au filtre." : "Aucun compétiteur inscrit." }}
    </p>
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

    <div v-if="canWrite" class="mt-4 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm" data-testid="add-members">
      <div class="flex flex-wrap items-center gap-2">
        <b class="text-[13.5px]">➕ Inscrire des adhérents</b>
        <UiButton variant="muted" small class="ml-auto" data-testid="load-group" @click="loadGroup"
          >🧗 Charger le groupe « Compétition »</UiButton
        >
        <UiButton variant="muted" small data-testid="toggle-add" :aria-expanded="adding" @click="adding = !adding">{{
          adding ? "Fermer" : "🔍 Rechercher un adhérent"
        }}</UiButton>
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
        @remove="remove"
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
        <div class="flex gap-2">
          <UiButton type="submit" data-testid="results-ok" :disabled="!resultsUrl.trim()">🔍 Chercher</UiButton>
          <UiButton variant="muted" @click="askUrl = false">Annuler</UiButton>
        </div>
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
