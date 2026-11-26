<script setup lang="ts">
/* One of the poster's drawings (posterArt/: a volume and four holds, single-colour line art), inline so it takes the
   text colour (`currentColor`) set by the poster's theme. */
import { computed } from "vue";

export type ArtName = "volume" | "crimp" | "sloper_1" | "sloper_2" | "sloper_3";

// Bundled with the app, as text: same origin, so the PNG capture embeds them
const DRAWINGS: Record<string, string> = import.meta.glob("./posterArt/*.svg", { query: "?raw", import: "default", eager: true });

const props = defineProps<{ name: ArtName }>();
const drawing = computed(() => DRAWINGS[`./posterArt/${props.name}.svg`] ?? "");
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- our own SVG files, bundled at build time: never user data -->
  <span class="inline-block [&_svg]:block [&_svg]:h-full [&_svg]:w-full [&_svg]:fill-current" v-html="drawing" />
</template>
