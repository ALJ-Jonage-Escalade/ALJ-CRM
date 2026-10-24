<script setup lang="ts">
export type Tone = "neutral" | "success" | "warning" | "danger";
defineProps<{ tone: Tone }>();
</script>

<template>
  <span
    :class="[
      'inline-block rounded-full px-2.5 py-0.5 text-[11.5px] font-bold whitespace-nowrap text-white',
      { neutral: 'bg-slate-400', success: 'bg-emerald-600', warning: 'bg-amber-500', danger: 'bg-red-600' }[tone],
    ]"
    ><slot
  /></span>
</template>
