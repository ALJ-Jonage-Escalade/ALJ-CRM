<script setup lang="ts">
/* The competitions on a month: a grid of weeks with one bar per competition (across its days) from md up, the month's
   list on phones. Drawing only: the layout is in calendar.ts, opening a competition is the page's. */
import { computed, ref } from "vue";
import { SOFT, SOLID } from "../../../components/ui/palette";
import UiButton from "../../../components/ui/UiButton.vue";
import {
  agendaDays,
  calendarColor,
  competitionDays,
  initialMonth,
  layoutWeek,
  LEGEND,
  monthAgenda,
  monthTitle,
  monthWeeks,
  shiftMonth,
  WEEKDAYS,
  type CalendarBar,
} from "./calendar";
import { isArchived, period, todayIso, type Competition } from "../competitions";

const props = defineProps<{
  competitions: readonly Competition[];
  selectedId?: string;
}>();
// Also when it is the selected one already (the page then goes back to the cards without a URL change)
const emit = defineEmits<{ open: [competition: Competition] }>();

const today = todayIso();
const selected = computed(() => props.competitions.find((c) => String(c.id) === props.selectedId));
const shown = ref(initialMonth(selected.value, today));

const weeks = computed(() => monthWeeks(shown.value, today).map((days) => ({ days, ...layoutWeek(props.competitions, days[0]!.dateIso) })));
const agenda = computed(() => monthAgenda(props.competitions, shown.value));

function barText(c: Competition): string {
  return [c.nom, c.lieu || "lieu non précisé", period(c)].join(" · ");
}

function barClass(bar: CalendarBar): string[] {
  return [
    "relative z-10 mx-1 my-px flex min-w-0 cursor-pointer items-center gap-0.5 rounded-md border px-1.5 text-left text-[11px] font-semibold",
    "transition hover:brightness-95",
    SOFT[calendarColor(bar.competition)],
    bar.continuesBefore ? "-ml-px rounded-l-none border-l-0" : "",
    bar.continuesAfter ? "-mr-px rounded-r-none border-r-0" : "",
    isArchived(bar.competition) ? "opacity-60" : "",
    String(bar.competition.id) === props.selectedId ? "ring-2 ring-accent" : "",
  ];
}

const isOnToday = (c: Competition): boolean => {
  const days = competitionDays(c);
  return !!days && days[0] <= today && today <= days[1];
};
</script>

<template>
  <div class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm md:p-4" data-testid="comp-calendar">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <h2 class="text-base font-bold text-slate-900" data-testid="calendar-title">{{ monthTitle(shown) }}</h2>
        <UiButton variant="muted" small data-testid="calendar-today" @click="shown = initialMonth(undefined, today)">Aujourd'hui</UiButton>
      </div>
      <div class="flex items-center gap-1.5">
        <UiButton variant="muted" small data-testid="prev-month" aria-label="Mois précédent" @click="shown = shiftMonth(shown, -1)">
          ‹ Précédent
        </UiButton>
        <UiButton variant="muted" small data-testid="next-month" aria-label="Mois suivant" @click="shown = shiftMonth(shown, 1)">
          Suivant ›
        </UiButton>
      </div>
    </div>

    <ul
      class="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600"
      aria-label="Disciplines"
      data-testid="calendar-legend"
    >
      <li v-for="entry in LEGEND" :key="entry.label" class="flex items-center gap-1">
        <span :class="['inline-block size-2.5 rounded-full', SOLID[entry.color]]" aria-hidden="true" />
        {{ entry.label }}
      </li>
    </ul>

    <!-- Desktop: the month's weeks, a CSS grid per week (row 1 the day numbers, then one row per lane) -->
    <div class="hidden overflow-hidden rounded-lg border border-slate-200 md:block" data-testid="calendar-grid">
      <div class="grid grid-cols-7 border-b border-slate-200 bg-slate-50" aria-hidden="true">
        <div v-for="name in WEEKDAYS" :key="name" class="py-1.5 text-center text-xs font-bold text-slate-600 capitalize">{{ name }}</div>
      </div>
      <div
        v-for="week in weeks"
        :key="week.days[0]!.dateIso"
        class="grid min-h-24 grid-cols-7 border-b border-slate-200 pb-1"
        :style="{ gridTemplateRows: `1.75rem repeat(${week.lanes}, 1.5rem) 1fr` }"
        data-testid="calendar-week"
      >
        <div
          v-for="(day, column) in week.days"
          :key="day.dateIso"
          :class="['border-l border-slate-200 px-1.5 pt-1', day.inMonth ? 'bg-white text-slate-700' : 'bg-slate-50 text-slate-400']"
          :style="{ gridColumn: column + 1, gridRow: '1 / -1' }"
          :aria-current="day.isToday ? 'date' : undefined"
          data-testid="calendar-day"
        >
          <span :class="['inline-block rounded px-1 text-xs font-bold', day.isToday ? 'bg-accent text-white' : '']">
            {{ day.dayNumber }}
          </span>
        </div>
        <button
          v-for="bar in week.bars"
          :key="bar.competition.id"
          type="button"
          :class="barClass(bar)"
          :style="{ gridColumn: `${bar.startCol + 1} / span ${bar.span}`, gridRow: bar.lane + 2 }"
          :title="barText(bar.competition)"
          :aria-label="barText(bar.competition)"
          data-testid="calendar-comp-chip"
          @click="emit('open', bar.competition)"
        >
          <span v-if="bar.continuesBefore" aria-hidden="true">‹</span>
          <span class="min-w-0 flex-1 truncate">{{ bar.competition.nom }}</span>
          <span v-if="bar.continuesAfter" aria-hidden="true">›</span>
        </button>
      </div>
    </div>

    <!-- Phones: the month's competitions as a list -->
    <ul class="flex flex-col gap-1.5 md:hidden" data-testid="calendar-agenda">
      <li v-if="!agenda.length" class="py-4 text-center text-sm text-slate-500">Aucune compétition ce mois-ci.</li>
      <li v-for="c in agenda" :key="c.id">
        <button
          type="button"
          :class="[
            'flex w-full cursor-pointer items-start gap-2 rounded-lg border border-slate-200 px-2.5 py-2 text-left hover:bg-slate-50',
            isArchived(c) ? 'opacity-60' : '',
            String(c.id) === selectedId ? 'ring-2 ring-accent' : '',
          ]"
          data-testid="calendar-agenda-item"
          @click="emit('open', c)"
        >
          <span :class="['mt-1.5 inline-block size-2.5 shrink-0 rounded-full', SOLID[calendarColor(c)]]" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-1.5 text-xs font-semibold text-slate-500">
              {{ agendaDays(c) }}
              <span v-if="isOnToday(c)" class="rounded bg-accent px-1 text-[10px] font-bold text-white">Aujourd'hui</span>
            </span>
            <span class="block truncate text-sm font-bold text-slate-900">{{ c.nom }}</span>
            <span v-if="c.lieu" class="block truncate text-xs text-slate-500">{{ c.lieu }}</span>
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>
