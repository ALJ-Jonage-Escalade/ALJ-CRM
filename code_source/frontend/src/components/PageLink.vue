<script setup lang="ts">
/* Link to an office page: within the app (no reload) when the page is migrated, a plain link to the former page otherwise. */
import { computed } from "vue";
import { RouterLink, useRouter } from "vue-router";

const props = defineProps<{ href: string }>();
const router = useRouter();  // undefined in the components' tests mounted without a router
const inApp = computed(() => !!router && router.resolve(props.href).name !== undefined);
</script>

<template>
  <RouterLink v-if="inApp" :to="href"><slot /></RouterLink>
  <a v-else :href="href"><slot /></a>
</template>
