<script setup lang="ts">
/* Week view, Monday to Saturday from 9:00 to 22:00 (as the Excel grid). Wider than a phone: it scrolls sideways
   inside its frame. A click on a slot opens it. */
import { computed } from "vue";
import { HOUR_PX, HOURS, slotKind, week, type Kind, type Slot } from "./slots";

const props = defineProps<{ slots: readonly Slot[] }>();
const emit = defineEmits<{ open: [slot: Slot] }>();

const days = computed(() => week(props.slots));

const KIND_CLASS: Record<Kind, string> = {
  competition: "border-[#66BB6A] bg-[#E8F5E9] text-[#1B5E20]",
  perfectionnement: "border-[#EC407A] bg-[#FCE4EC] text-[#880E4F]",
  cours: "border-[#7986CB] bg-[#E8EAF6] text-[#1A237E]",
  "autonome-bloc": "border-[#FFA726] bg-[#FFF3E0] text-[#E65100]",
  autonome: "border-[#9CA3AF] bg-[#F3F4F6] text-[#374151]",
};

function hour(h: number): string {
  return `${String(h).padStart(2, "0")}h00`;
}

function tip(slot: Slot): string {
  const coaches = slot.encadrants.join(" / ");
  return [`${slot.groupe} (${slot.horaires})`, coaches && `Enc. : ${coaches}`, "Cliquez pour modifier"].filter(Boolean).join("\n");
}
</script>

<template>
  <div
    class="flex overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm print:overflow-visible print:rounded-none print:border-black print:shadow-none"
  >
    <div class="w-14 shrink-0 border-r border-slate-200 bg-slate-50" aria-hidden="true">
      <div class="flex h-10 items-center justify-center border-b border-slate-200 text-[11px] font-bold text-slate-500">HEURE</div>
      <div
        v-for="h in HOURS"
        :key="h"
        class="box-border flex justify-center border-b border-dashed border-slate-200 pt-0.5 text-[11px] font-semibold text-slate-500"
        :style="{ height: `${HOUR_PX}px` }"
      >
        {{ hour(h) }}
      </div>
    </div>
    <div class="grid flex-1 grid-cols-[repeat(6,minmax(140px,1fr))] print:grid-cols-6">
      <section
        v-for="{ day, placed } in days"
        :key="day"
        :data-testid="`day-${day}`"
        :aria-label="day"
        class="flex flex-col border-r border-slate-200"
      >
        <h3
          class="flex h-10 items-center justify-center border-b border-slate-200 bg-slate-100 text-[13px] font-bold tracking-wide text-slate-800 uppercase"
        >
          {{ day }}
        </h3>
        <div
          class="relative bg-[linear-gradient(to_bottom,#E2E8F0_1px,transparent_1px)]"
          :style="{ height: `${HOURS.length * HOUR_PX}px`, backgroundSize: `100% ${HOUR_PX}px` }"
        >
          <button
            v-for="p in placed"
            :key="p.slot.id"
            type="button"
            data-testid="slot-card"
            :title="tip(p.slot)"
            :class="[
              'absolute flex cursor-pointer flex-col justify-between overflow-hidden rounded-lg border-[1.5px] px-2 py-1.5 text-left text-[11.5px] leading-snug shadow-sm',
              'transition hover:z-20 hover:-translate-y-px hover:shadow-md print:shadow-none',
              KIND_CLASS[slotKind(p.slot)],
            ]"
            :style="{
              top: `${p.top}px`,
              height: `${p.height}px`,
              left: `calc(${(p.lane * 100) / p.lanes}% + 2px)`,
              width: `calc(${100 / p.lanes}% - 4px)`,
            }"
            @click="emit('open', p.slot)"
          >
            <span class="block min-w-0">
              <b class="block truncate text-[11px]">{{ p.slot.groupe }}</b>
              <span class="block text-[10.5px] opacity-90">🕒 {{ p.slot.horaires }}</span>
            </span>
            <span v-if="p.slot.encadrants.length" class="block truncate text-[10px] opacity-85">
              👤 {{ p.slot.encadrants.join(" / ") }}
            </span>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>
