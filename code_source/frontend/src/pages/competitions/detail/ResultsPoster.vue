<script setup lang="ts">
/* The results poster itself, drawn at its real size (1080 px wide, as tall as its blocks) to be turned into a PNG:
   the club's logo and the competition, then one block per category. Colours: posterTheme.ts; the result badges
   are those of the competition page (palette.ts). */
import { computed } from "vue";
import { SOFT } from "../../../components/ui/palette";
import { periodText, type Competition, type Participant } from "../competitions";
import { posterBlocks } from "./poster";
import { posterThemeStyle } from "./posterTheme";

/* Served by FastAPI next to the PWA files (web/assets), same origin: the PNG can embed it */
const LOGO_URL = "/annuaire/assets/logo.png";

const props = defineProps<{ competition: Competition; participants: readonly Participant[] }>();

const blocks = computed(() => posterBlocks(props.participants));
const where = computed(() => [periodText(props.competition), props.competition.lieu].filter(Boolean).join(" · "));
const themeStyle = posterThemeStyle();
</script>

<template>
  <div class="w-[1080px] bg-(--poster-background) px-16 py-14 font-sans text-(--poster-text)" :style="themeStyle">
    <header class="flex items-center gap-8 border-b-[6px] border-(--poster-accent) pb-8">
      <img :src="LOGO_URL" alt="" class="h-36 w-36 shrink-0 object-contain" />
      <div class="min-w-0">
        <p class="text-[34px] font-extrabold tracking-[0.2em] text-(--poster-accent) uppercase">Résultats</p>
        <h1 class="mt-1 text-[52px] leading-tight font-extrabold text-(--poster-primary)">{{ competition.nom }}</h1>
        <p class="mt-2 text-[30px] text-(--poster-muted)">{{ where }}</p>
      </div>
    </header>

    <section v-for="block in blocks" :key="block.title" class="mt-10">
      <h2 class="mb-3 text-[40px] font-extrabold text-(--poster-accent)">{{ block.title }}</h2>
      <div v-for="(line, index) in block.lines" :key="index" class="flex items-center justify-between gap-6 px-6 py-3 text-[34px]">
        <span class="min-w-0 font-bold text-(--poster-primary)">{{ line.name }}</span>
        <!-- The result badge of the competition page (UiBadge soft), at the poster's size -->
        <span :class="['shrink-0 rounded-xl border-2 px-4 py-1 font-bold whitespace-nowrap', SOFT[line.color]]">{{ line.place }}</span>
      </div>
    </section>

    <footer class="mt-12 border-t-2 border-(--poster-divider) pt-6 text-[26px] font-bold text-(--poster-muted)">
      ALJ Escalade · Jonage
    </footer>
  </div>
</template>
