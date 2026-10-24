<script setup lang="ts">
defineProps<{ message: string }>();
</script>

<template>
  <div
    id="toast"
    data-testid="toast"
    role="status"
    aria-live="polite"
    :class="[
      'pointer-events-none fixed inset-x-4 bottom-20 z-50 mx-auto max-w-md rounded-xl bg-slate-900 px-4 py-3 text-center text-[13px] text-white shadow-lg transition-opacity md:bottom-6',
      message ? 'opacity-100' : 'opacity-0',
    ]"
  >
    {{ message }}
  </div>
</template>
