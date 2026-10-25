<script setup lang="ts">
/* A labelled value of a status grid. */
defineProps<{ label: string }>();
</script>

<template>
  <div class="min-w-0 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
    <div class="text-[11.5px] font-semibold text-slate-500 uppercase">{{ label }}</div>
    <div class="mt-0.5 font-bold break-words"><slot /></div>
  </div>
</template>
