<script setup lang="ts">
/* Link to an office page: a RouterLink (no reload) for a route of the app, a plain <a> for any other address and when
   mounted without a router (the components' tests). */
import { computed } from "vue";
import { RouterLink, useRouter } from "vue-router";

const props = defineProps<{ href: string }>();
const router = useRouter(); // undefined in the components' tests mounted without a router
const inApp = computed(() => !!router && router.resolve(props.href).name !== undefined);
</script>

<template>
  <RouterLink v-if="inApp" :to="href"><slot /></RouterLink>
  <a v-else :href="href"><slot /></a>
</template>
