<script setup lang="ts">
/* Club name and "Bureau" with the version: head of the side menu, and of the full-screen login (large). */
import VersionBadge from "./VersionBadge.vue";

defineProps<{ large?: boolean }>();
</script>

<template>
  <div>
    <b :class="['block text-slate-50', large ? 'text-xl' : 'text-base']">🧗 ALJ Escalade</b>
    <span :class="['mt-0.5 block text-slate-400', large ? 'text-sm' : 'text-xs']">
      Bureau ·
      <VersionBadge />
    </span>
  </div>
</template>
