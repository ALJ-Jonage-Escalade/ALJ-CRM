<script setup lang="ts">
/* « Bilan » (coaches and admins): what each competitor owes and paid for the season's competitions (balance.ts), with
   the season's totals and a spreadsheet export. Desktop: the competitors next to the selected one's detail, as on the
   former office page; phones: cards opening in place. Computed from the competitions only: readable offline. */
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import UiBadge from "../../components/ui/UiBadge.vue";
import type { BadgeColor } from "../../components/ui/palette";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import UiTile from "../../components/ui/UiTile.vue";
import { useMediaQuery } from "../../composables/media";
import { csvBlob } from "../../lib/csv";
import { saveFile } from "../../lib/download";
import { formatEuros } from "../../lib/format";
import { balanceCsv, balanceLabel, balances, searchBalances, seasonOf, seasons, totals, type Balance } from "./balance";
import { discipline, disciplineColor, payment, period, todayIso, type Competition } from "./competitions";
import { plural } from "../../lib/text";

const props = defineProps<{ competitions: readonly Competition[] }>();

const today = todayIso();
const seasonList = computed(() => seasons(props.competitions, today));
const season = ref(seasonOf(today)); // the current one, listed even without competitions
const search = ref("");
const all = computed(() => balances(props.competitions, season.value, today));
const shown = computed(() => searchBalances(all.value, search.value));
const sum = computed(() => totals(shown.value));
const keyOf = (b: { adherentId: number | null; nom: string; prenom: string }) => String(b.adherentId ?? `${b.nom}|${b.prenom}`);
// The card opened on phones, the competitor detailed on desktop (the first one until another is picked)
const open = ref<string | null>(null);
const selected = computed(() => shown.value.find((b) => keyOf(b) === open.value) ?? shown.value[0] ?? null);

const wide = useMediaQuery("(min-width: 768px)"); // Tailwind's md

function toggle(b: Balance): void {
  // On desktop a click only selects: the detail stays shown
  open.value = open.value === keyOf(b) && !wide.value ? null : keyOf(b);
}

function exportCsv(): void {
  saveFile(csvBlob(balanceCsv(shown.value)), `bilan_competitions_${season.value}.csv`);
}

const TONE_COLOR = { ok: "green", due: "red", credit: "violet" } satisfies Record<string, BadgeColor>;
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
        <div class="text-lg font-extrabold">{{ formatEuros(sum.due) }}</div>
        <div class="text-[11px] font-semibold text-slate-500">Total dû</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-center">
        <div class="text-lg font-extrabold text-green-600">{{ formatEuros(sum.paid) }}</div>
        <div class="text-[11px] font-semibold text-slate-500">Total réglé</div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-center">
        <div :class="['text-lg font-extrabold', sum.remaining > 0 ? 'text-red-600' : 'text-green-600']">
          {{ formatEuros(sum.remaining) }}
        </div>
        <div class="text-[11px] font-semibold text-slate-500">Reste à payer</div>
      </div>
    </div>
    <div
      class="md:grid md:grid-cols-[minmax(0,340px)_minmax(0,1fr)] md:items-start md:gap-4 xl:grid-cols-[320px_minmax(0,1fr)] 2xl:grid-cols-[380px_minmax(0,1fr)]"
    >
      <!-- The competitors: on desktop a panel scrolling on its own next to the selected one's detail, on phones cards
           opening in place -->
      <ul
        class="flex flex-col gap-2 md:sticky md:top-3 md:max-h-[calc(100dvh-1.5rem)] md:overflow-y-auto md:rounded-xl md:border md:border-slate-200 md:bg-white md:p-3 md:shadow-sm"
        aria-label="Compétiteurs"
      >
        <li
          v-for="b in shown"
          :key="keyOf(b)"
          data-testid="balance-card"
          :class="[
            'rounded-xl border bg-white px-3.5 py-2.5 shadow-sm',
            wide && selected && keyOf(selected) === keyOf(b) ? 'border-accent' : 'border-slate-200',
          ]"
        >
          <button
            type="button"
            class="flex w-full cursor-pointer items-start justify-between gap-2 text-left"
            :aria-expanded="wide ? undefined : open === keyOf(b)"
            :aria-current="wide && selected && keyOf(selected) === keyOf(b) ? 'true' : undefined"
            data-testid="balance-toggle"
            @click="toggle(b)"
          >
            <span class="min-w-0">
              <b class="block text-[14.5px]" data-testid="balance-name">{{ b.nom }} {{ b.prenom }}</b>
              <span class="block text-xs text-slate-500">
                🪪 {{ b.licence || "sans licence" }} · 🏃 {{ b.lines.length }} épreuve{{ plural(b.lines.length) }}
                <template v-if="b.lines.some((l) => l.carriedOver)">· 🔄 Report</template>
                <template v-if="b.absent">· ⚠️ Absent</template>
              </span>
            </span>
            <UiBadge :color="TONE_COLOR[balanceLabel(b).tone]" variant="soft" class="shrink-0" data-testid="balance-state">
              {{ balanceLabel(b).text }}
            </UiBadge>
          </button>
          <ul
            v-if="!wide && (open === keyOf(b) || search)"
            class="mt-2 border-t border-slate-100 pt-1.5 text-xs"
            data-testid="balance-lines"
          >
            <li
              v-for="l in b.lines"
              :key="l.competition.id"
              class="flex flex-wrap items-center justify-between gap-1 border-b border-dashed border-slate-100 py-1"
            >
              <RouterLink
                :to="{ query: { id: String(l.competition.id) } }"
                class="font-semibold text-slate-700 no-underline hover:text-accent"
              >
                🏆 {{ l.competition.nom }}
                <span class="font-normal text-slate-500">· {{ period(l.competition) }}</span>
              </RouterLink>
              <span>
                Dû :
                <b>{{ formatEuros(l.due) }}</b>
                · Payé :
                <b>{{ formatEuros(l.paid) }}</b>
                · {{ payment(l.status).label }}
                <template v-if="l.present">· ✓ Présent</template>
              </span>
            </li>
            <li class="flex justify-between pt-1 font-bold text-slate-700">
              <span>Total</span>
              <span>Dû : {{ formatEuros(b.due) }} · Payé : {{ formatEuros(b.paid) }}</span>
            </li>
          </ul>
        </li>
        <li v-if="!shown.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">
          {{
            all.length ? "Aucun compétiteur ne correspond à la recherche." : `Aucune inscription en compétition pour la saison ${season}.`
          }}
        </li>
      </ul>

      <!-- Desktop: the selected competitor's competitions and payments -->
      <div v-if="wide && selected" class="flex flex-col gap-3" data-testid="balance-detail">
        <UiCard>
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div class="min-w-0">
              <h2 class="m-0 text-lg font-extrabold text-slate-800">👤 {{ selected.nom }} {{ selected.prenom }}</h2>
              <p class="m-0 mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500" data-testid="balance-contact">
                <span>
                  🪪 Licence FFME :
                  <b>{{ selected.licence || "sans licence" }}</b>
                </span>
                <span v-if="selected.group">
                  🏷️ Catégorie / Groupe :
                  <b>{{ selected.group }}</b>
                </span>
                <a v-if="selected.email" :href="`mailto:${selected.email}`" class="text-accent no-underline hover:underline">
                  ✉️ {{ selected.email }}
                </a>
                <a v-if="selected.phone" :href="`tel:${selected.phone}`" class="text-accent no-underline hover:underline">
                  📞 {{ selected.phone }}
                </a>
              </p>
            </div>
            <UiBadge :color="TONE_COLOR[balanceLabel(selected).tone]" variant="soft">{{ balanceLabel(selected).text }}</UiBadge>
          </div>
          <div class="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
            <UiTile label="Épreuves">{{ selected.lines.length }}</UiTile>
            <UiTile label="Total dû">{{ formatEuros(selected.due) }}</UiTile>
            <UiTile label="Total réglé">
              <span class="text-green-600">{{ formatEuros(selected.paid) }}</span>
            </UiTile>
            <UiTile label="Reste à payer">
              <span :class="selected.remaining > 0 ? 'text-red-600' : 'text-green-600'">
                {{ formatEuros(Math.max(selected.remaining, 0)) }}
              </span>
            </UiTile>
          </div>
        </UiCard>
        <UiCard>
          <h3 class="m-0 mb-2.5 text-[15px] font-bold text-slate-800">Détail des épreuves ({{ selected.lines.length }})</h3>
          <ul class="flex flex-col gap-2" data-testid="balance-detail-lines">
            <li
              v-for="l in selected.lines"
              :key="l.competition.id"
              class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2.5"
            >
              <div class="min-w-60 flex-1">
                <div class="flex flex-wrap items-center gap-1.5">
                  <b class="text-sm text-slate-800">{{ l.competition.nom }}</b>
                  <UiBadge v-if="discipline(l.competition)" :color="disciplineColor(discipline(l.competition))" variant="soft">
                    {{ discipline(l.competition) }}
                  </UiBadge>
                  <UiBadge v-if="l.carriedOver" color="violet" variant="soft">🔄 Report</UiBadge>
                  <UiBadge v-if="l.absent" color="red" variant="soft">⚠️ Absent</UiBadge>
                  <UiBadge v-else-if="l.present && !l.ranking" color="green" variant="soft">✓ Présent</UiBadge>
                </div>
                <div class="mt-1 flex flex-wrap gap-x-2.5 text-xs text-slate-500">
                  <span>📅 {{ period(l.competition) }}</span>
                  <span v-if="l.competition.lieu">📍 {{ l.competition.lieu }}</span>
                  <span>
                    💰 Tarif :
                    <template v-if="l.carriedOver">
                      <del>{{ formatEuros(Number(l.competition.prix ?? 0)) }}</del>
                      <b class="text-violet-700">({{ formatEuros(0) }} dû)</b>
                    </template>
                    <b v-else>{{ formatEuros(l.due) }}</b>
                  </span>
                </div>
              </div>
              <div class="flex flex-wrap items-center gap-3">
                <span class="flex min-w-24 flex-col items-center text-xs font-bold text-slate-700">
                  {{ l.ranking || "—" }}
                  <span v-if="l.ranking && l.participant.categorie_ffme" class="text-[10.5px] font-semibold text-slate-500">
                    {{ l.participant.categorie_ffme }}
                  </span>
                </span>
                <span class="flex min-w-32 flex-col items-end">
                  <UiBadge :color="payment(l.status).color" variant="soft">
                    {{ payment(l.status).label }} · {{ formatEuros(l.paid) }}
                  </UiBadge>
                  <span v-if="l.participant.commande_helloasso" class="mt-0.5 text-[11px] text-slate-500">
                    Cde :
                    <code>{{ l.participant.commande_helloasso }}</code>
                  </span>
                </span>
                <RouterLink
                  :to="{ query: { id: String(l.competition.id) } }"
                  class="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 no-underline hover:border-accent hover:text-accent"
                >
                  🔍 Voir l'épreuve
                </RouterLink>
              </div>
            </li>
          </ul>
        </UiCard>
      </div>
    </div>
  </section>
</template>
