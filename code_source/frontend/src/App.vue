<script setup lang="ts">
import DevBanner from "./components/DevBanner.vue";
import UiDialogHost from "./components/ui/UiDialogHost.vue";
</script>

<template>
  <RouterView />
  <DevBanner />
  <UiDialogHost />
</template>
