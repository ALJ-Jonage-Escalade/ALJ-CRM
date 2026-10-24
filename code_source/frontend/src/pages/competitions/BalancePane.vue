<script setup lang="ts">
/* « Bilan » (coaches and admins): what each competitor owes and paid for the season's competitions (balance.ts), with
   the season's totals and a spreadsheet export. Computed from the competitions only: readable offline. */
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import UiButton from "../../components/ui/UiButton.vue";
import { csvBlob } from "../../lib/csv";
import { saveFile } from "../../lib/download";
import { balanceCsv, balanceLabel, balances, searchBalances, seasonOf, seasons, totals } from "./balance";
import { euros, payment, period, todayIso, type Competition } from "./competitions";

const props = defineProps<{ competitions: readonly Competition[] }>();

const today = todayIso();
const seasonList = computed(() => seasons(props.competitions, today));
const season = ref(seasonOf(today)); // the current one, listed even without competitions
const search = ref("");
const all = computed(() => balances(props.competitions, season.value, today));
const shown = computed(() => searchBalances(all.value, search.value));
const sum = computed(() => totals(shown.value));
const open = ref<string | null>(null);
const keyOf = (b: { adherentId: number | null; nom: string; prenom: string }) => String(b.adherentId ?? `${b.nom}|${b.prenom}`);

function exportCsv(): void {
  saveFile(csvBlob(balanceCsv(shown.value)), `bilan_competitions_${season.value}.csv`);
}

const TONE = {
  ok: "border-green-200 bg-green-50 text-green-700",
  due: "border-red-200 bg-red-50 text-red-700",
  credit: "border-violet-200 bg-violet-50 text-violet-700",
};
</script>

<template>
  <section aria-label="Bilan de la saison" data-testid="balance-pane">
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <label class="text-xs font-semibold text-slate-500" for="balance-season">Saison</label>
      <select
        id="balance-season"
        v-model="season"
        data-testid="balance-season"
        class="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[13px]"
      >
        <option v-for="s in seasonList" :key="s" :value="s">{{ s }}</option>
      </select>
      <input
        v-model="search"
        type="search"
        data-testid="balance-search"
        placeholder="Rechercher un compétiteur…"
        class="min-w-48 flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px]"
      />
      <UiButton variant="muted" small data-testid="balance-export" :disabled="!shown.length" @click="exportCsv">📥 Export CSV</UiButton>
    </div>
    <div class="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
      <div class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-center">
        <div class="text-lg font-extrabold" data-testid="balance-athletes">{{ shown.length }}</div>
        <div class="text-[11px] font-semibold text-slate-500">Compétiteurs</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-center">
        <div class="text-lg font-extrabold">{{ euros(sum.due) }}</div>
        <div class="text-[11px] font-semibold text-slate-500">Total dû</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-center">
        <div class="text-lg font-extrabold text-green-600">{{ euros(sum.paid) }}</div>
        <div class="text-[11px] font-semibold text-slate-500">Total réglé</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-center">
        <div :class="['text-lg font-extrabold', sum.remaining > 0 ? 'text-red-600' : 'text-green-600']">{{ euros(sum.remaining) }}</div>
        <div class="text-[11px] font-semibold text-slate-500">Reste à payer</div>
      </div>
    </div>
    <ul class="grid gap-2 xl:grid-cols-2">
      <li
        v-for="b in shown"
        :key="keyOf(b)"
        data-testid="balance-card"
        class="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 shadow-sm"
      >
        <button
          type="button"
          class="flex w-full cursor-pointer items-start justify-between gap-2 text-left"
          :aria-expanded="open === keyOf(b)"
          data-testid="balance-toggle"
          @click="open = open === keyOf(b) ? null : keyOf(b)"
        >
          <span class="min-w-0">
            <b class="block text-[14.5px]" data-testid="balance-name">{{ b.nom }} {{ b.prenom }}</b>
            <span class="block text-xs text-slate-500">
              🪪 {{ b.licence || "sans licence" }} · 🏃 {{ b.lines.length }} épreuve{{ b.lines.length > 1 ? "s" : "" }}
              <template v-if="b.lines.some((l) => l.carriedOver)"> · 🔄 Report</template>
              <template v-if="b.absent"> · ⚠️ Absent</template>
            </span>
          </span>
          <span
            :class="['shrink-0 rounded-md border px-2 py-0.5 text-xs font-bold', TONE[balanceLabel(b, euros).tone]]"
            data-testid="balance-state"
            >{{ balanceLabel(b, euros).text }}</span
          >
        </button>
        <ul v-if="open === keyOf(b) || search" class="mt-2 border-t border-slate-100 pt-1.5 text-xs" data-testid="balance-lines">
          <li
            v-for="l in b.lines"
            :key="l.competition.id"
            class="flex flex-wrap items-center justify-between gap-1 border-b border-dashed border-slate-100 py-1"
          >
            <RouterLink
              :to="{ query: { id: String(l.competition.id) } }"
              class="font-semibold text-slate-700 no-underline hover:text-accent"
              >🏆 {{ l.competition.nom }} <span class="font-normal text-slate-500">· {{ period(l.competition) }}</span></RouterLink
            >
            <span
              >Dû : <b>{{ euros(l.due) }}</b> · Payé : <b>{{ euros(l.paid) }}</b> · {{ payment(l.status).label
              }}<template v-if="l.present"> · ✓ Présent</template></span
            >
          </li>
          <li class="flex justify-between pt-1 font-bold text-slate-700">
            <span>Total</span><span>Dû : {{ euros(b.due) }} · Payé : {{ euros(b.paid) }}</span>
          </li>
        </ul>
      </li>
      <li v-if="!shown.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">
        {{ all.length ? "Aucun compétiteur ne correspond à la recherche." : `Aucune inscription en compétition pour la saison ${season}.` }}
      </li>
    </ul>
  </section>
</template>
