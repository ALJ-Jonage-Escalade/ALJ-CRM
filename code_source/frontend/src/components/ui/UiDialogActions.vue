<script setup lang="ts">
/* The button row at the bottom of a dialog or form: « Annuler » first, the main action last. On a phone the buttons
   share the whole width (big targets for the thumb); from sm up they keep their size and sit on the right, the main
   action in the bottom-right corner. */
</script>

<template>
  <div class="flex flex-wrap gap-2 sm:justify-end [&>*]:flex-1 sm:[&>*]:flex-none">
    <slot />
  </div>
</template>
