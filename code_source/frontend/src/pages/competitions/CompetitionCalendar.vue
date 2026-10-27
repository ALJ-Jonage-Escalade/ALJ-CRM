<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import UiButton from "../../components/ui/UiButton.vue";
import { discipline, type Competition } from "./competitions";

const props = defineProps<{
  competitions: readonly Competition[];
}>();

const router = useRouter();

const currentYear = ref(new Date().getFullYear());
const currentMonth = ref(new Date().getMonth()); // 0-indexed

const MONTH_NAMES = [
  "Janvier",
  "Février",
  "Mars",
  "Avril",
  "Mai",
  "Juin",
  "Juillet",
  "Août",
  "Septembre",
  "Octobre",
  "Novembre",
  "Décembre",
];
const DAY_NAMES = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

const monthTitle = computed(() => `${MONTH_NAMES[currentMonth.value]} ${currentYear.value}`);

function prevMonth(): void {
  if (currentMonth.value === 0) {
    currentMonth.value = 11;
    currentYear.value -= 1;
  } else {
    currentMonth.value -= 1;
  }
}

function nextMonth(): void {
  if (currentMonth.value === 11) {
    currentMonth.value = 0;
    currentYear.value += 1;
  } else {
    currentMonth.value += 1;
  }
}

function goToToday(): void {
  const now = new Date();
  currentYear.value = now.getFullYear();
  currentMonth.value = now.getMonth();
}

interface CalendarDay {
  dateIso: string;
  dayNumber: number;
  inCurrentMonth: boolean;
  isToday: boolean;
  competitions: Competition[];
}

const calendarDays = computed<CalendarDay[]>(() => {
  const year = currentYear.value;
  const month = currentMonth.value;
  const firstDayOfMonth = new Date(year, month, 1);
  const lastDayOfMonth = new Date(year, month + 1, 0);

  // Day of week: 0 = Sunday, 1 = Monday, ... Convert to Monday = 0
  let startOffset = firstDayOfMonth.getDay() - 1;
  if (startOffset < 0) {
    startOffset = 6;
  }

  const totalDays = lastDayOfMonth.getDate();
  const prevMonthLastDate = new Date(year, month, 0).getDate();

  const nowIso = new Date().toISOString().slice(0, 10);
  const days: CalendarDay[] = [];

  // Previous month padding
  for (let i = startOffset - 1; i >= 0; i--) {
    const d = prevMonthLastDate - i;
    const m = month === 0 ? 12 : month;
    const y = month === 0 ? year - 1 : year;
    const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    days.push({
      dateIso: iso,
      dayNumber: d,
      inCurrentMonth: false,
      isToday: iso === nowIso,
      competitions: getCompetitionsForDate(iso),
    });
  }

  // Current month days
  for (let d = 1; d <= totalDays; d++) {
    const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    days.push({
      dateIso: iso,
      dayNumber: d,
      inCurrentMonth: true,
      isToday: iso === nowIso,
      competitions: getCompetitionsForDate(iso),
    });
  }

  // Next month padding to complete 35 or 42 cells
  const remaining = (7 - (days.length % 7)) % 7;
  for (let d = 1; d <= remaining; d++) {
    const m = month === 11 ? 1 : month + 2;
    const y = month === 11 ? year + 1 : year;
    const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    days.push({
      dateIso: iso,
      dayNumber: d,
      inCurrentMonth: false,
      isToday: iso === nowIso,
      competitions: getCompetitionsForDate(iso),
    });
  }

  return days;
});

function getCompetitionsForDate(dateIso: string): Competition[] {
  return props.competitions.filter((c) => {
    const start = c.date_competition?.slice(0, 10) ?? "";
    const end = c.date_fin?.slice(0, 10) || start;
    if (!start) {
      return false;
    }
    return dateIso >= start && dateIso <= end;
  });
}

function openComp(c: Competition): void {
  void router.push({ query: { id: String(c.id) } });
}

const DISCIPLINE_BG: Record<string, string> = {
  bloc: "bg-purple-100 text-purple-800 border-purple-300 hover:bg-purple-200",
  difficulté: "bg-blue-100 text-blue-800 border-blue-300 hover:bg-blue-200",
  vitesse: "bg-amber-100 text-amber-800 border-amber-300 hover:bg-amber-200",
  combiné: "bg-teal-100 text-teal-800 border-teal-300 hover:bg-teal-200",
};

function getDisciplineClass(c: Competition): string {
  const d = discipline(c).toLowerCase();
  return DISCIPLINE_BG[d] || "bg-sky-100 text-sky-800 border-sky-300 hover:bg-sky-200";
}
</script>

<template>
  <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="comp-calendar">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <h2 class="text-base font-bold text-slate-900" data-testid="calendar-title">{{ monthTitle }}</h2>
        <UiButton variant="muted" small @click="goToToday">Aujourd'hui</UiButton>
      </div>
      <div class="flex items-center gap-1.5">
        <UiButton variant="muted" small data-testid="prev-month" @click="prevMonth">‹ Précédent</UiButton>
        <UiButton variant="muted" small data-testid="next-month" @click="nextMonth">Suivant ›</UiButton>
      </div>
    </div>

    <!-- Légende des disciplines -->
    <div class="mb-3 flex flex-wrap items-center gap-2 text-xs">
      <span class="text-slate-500 font-semibold">Disciplines :</span>
      <span
        class="inline-flex items-center gap-1 rounded px-2 py-0.5 border text-[11px] font-bold bg-purple-100 text-purple-800 border-purple-300"
      >
        ● Bloc
      </span>
      <span
        class="inline-flex items-center gap-1 rounded px-2 py-0.5 border text-[11px] font-bold bg-blue-100 text-blue-800 border-blue-300"
      >
        ● Difficulté
      </span>
      <span
        class="inline-flex items-center gap-1 rounded px-2 py-0.5 border text-[11px] font-bold bg-amber-100 text-amber-800 border-amber-300"
      >
        ● Vitesse
      </span>
    </div>

    <!-- Grille des jours de la semaine -->
    <div class="grid grid-cols-7 gap-px border border-slate-200 bg-slate-200 rounded-lg overflow-hidden">
      <div v-for="name in DAY_NAMES" :key="name" class="bg-slate-50 py-1.5 text-center text-xs font-bold text-slate-600">
        {{ name }}
      </div>

      <!-- Cellules du calendrier -->
      <div
        v-for="day in calendarDays"
        :key="day.dateIso"
        :class="[
          'min-h-24 bg-white p-1.5 transition-colors flex flex-col',
          !day.inCurrentMonth ? 'bg-slate-50/50 text-slate-400' : 'text-slate-700',
          day.isToday ? 'ring-2 ring-accent ring-inset' : '',
        ]"
        data-testid="calendar-day"
      >
        <div class="flex items-center justify-between mb-1">
          <span :class="['text-xs font-bold inline-block px-1 rounded', day.isToday ? 'bg-accent text-white' : '']">
            {{ day.dayNumber }}
          </span>
        </div>

        <div class="flex flex-col gap-1 overflow-y-auto max-h-28">
          <button
            v-for="c in day.competitions"
            :key="c.id"
            type="button"
            :class="[
              'text-left text-[11px] font-semibold px-1.5 py-0.5 rounded border truncate cursor-pointer transition-colors',
              getDisciplineClass(c),
            ]"
            :title="`${c.nom} (${c.lieu || 'lieu non précisé'})`"
            data-testid="calendar-comp-chip"
            @click="openComp(c)"
          >
            {{ c.nom }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
