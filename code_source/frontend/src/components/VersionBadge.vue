<script lang="ts">
import { APP_VERSION, deployedVersion, forceUpdate } from "../lib/version";

// Asked once per page load, whatever the number of badges (side menu, phone footer)
let deployed: Promise<string | null> | null = null;
</script>

<script setup lang="ts">
/* App version; when another version is deployed, a click drops the caches and reloads. */
import { onMounted, ref } from "vue";

const online = ref<string | null>(null);
onMounted(async () => {
  deployed ??= deployedVersion();
  online.value = await deployed;
});
</script>

<template>
  <button
    v-if="online && online !== APP_VERSION"
    type="button"
    class="cursor-pointer text-[11px] font-semibold text-amber-400 underline"
    :title="`Une nouvelle version (v${online}) est en ligne : toucher pour mettre à jour`"
    @click="forceUpdate"
  >
    v{{ APP_VERSION }} ⬆ v{{ online }}
  </button>
  <span v-else class="text-[11px] font-semibold text-slate-400" :title="`Version de l'application : v${APP_VERSION}`"
    >v{{ APP_VERSION }}</span
  >
</template>
