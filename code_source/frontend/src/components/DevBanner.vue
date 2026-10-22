<script setup lang="ts">
import { isEmulator, runtime } from "../lib/runtime";
</script>

<template>
  <!-- Above the phone navigation bar; lets clicks through -->
  <div
    v-if="isEmulator"
    id="alj-dev-banner"
    role="status"
    class="pointer-events-none fixed inset-x-0 bottom-16 z-50 print:hidden bg-amber-700/90 px-3 py-1 text-center text-xs font-semibold text-white md:bottom-0"
  >DEV — Firebase emulator ({{ runtime.projectId }}): fake data</div>
</template>
