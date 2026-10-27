<script setup lang="ts">
/* A small coloured label: a status, a payment, a discipline… "solid": white text on a filled pill (a state);
   "soft": coloured text on a light tag (a piece of information). Colours: `palette.ts`.
   "h-fit" keeps the badge at its text height when a flex row stretches it (e.g. next to a multi-line name). */
import { SOFT, SOLID, type BadgeColor } from "./palette";

withDefaults(defineProps<{ color: BadgeColor; variant?: "solid" | "soft" }>(), { variant: "solid" });
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
