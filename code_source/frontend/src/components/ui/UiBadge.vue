<script setup lang="ts">
/* A small coloured label: a status, a payment, a discipline… "solid": white text on a filled pill (a state);
   "soft": coloured text on a light tag (a piece of information). The colour is a name of the palette below, never a
   Tailwind class: Tailwind only generates the classes written out in full in the source.
   "h-fit" keeps the badge at its text height when a flex row stretches it (e.g. next to a multi-line name). */
export type BadgeColor = "slate" | "green" | "amber" | "orange" | "red" | "pink" | "violet" | "indigo" | "blue" | "sky" | "teal";

withDefaults(defineProps<{ color: BadgeColor; variant?: "solid" | "soft" }>(), { variant: "solid" });

const SOLID: Record<BadgeColor, string> = {
  slate: "bg-slate-400",
  green: "bg-green-600",
  amber: "bg-amber-600",
  orange: "bg-orange-600",
  red: "bg-red-600",
  pink: "bg-pink-600",
  violet: "bg-violet-600",
  indigo: "bg-indigo-600",
  blue: "bg-blue-600",
  sky: "bg-sky-600",
  teal: "bg-teal-600",
};

const SOFT: Record<BadgeColor, string> = {
  slate: "border-slate-200 bg-slate-100 text-slate-600",
  green: "border-green-200 bg-green-50 text-green-700",
  amber: "border-amber-200 bg-amber-50 text-amber-800",
  orange: "border-orange-200 bg-orange-50 text-orange-800",
  red: "border-red-200 bg-red-50 text-red-700",
  pink: "border-pink-200 bg-pink-50 text-pink-800",
  violet: "border-violet-200 bg-violet-50 text-violet-700",
  indigo: "border-indigo-200 bg-indigo-50 text-indigo-800",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  sky: "border-sky-200 bg-sky-50 text-sky-700",
  teal: "border-teal-200 bg-teal-50 text-teal-700",
};
</script>

<template>
  <span
    :class="[
      'inline-block h-fit py-0.5 text-[11px] font-bold whitespace-nowrap',
      variant === 'solid' ? ['rounded-full px-2.5 text-white', SOLID[color]] : ['rounded-md border px-2', SOFT[color]],
    ]"
  >
    <slot />
  </span>
</template>
