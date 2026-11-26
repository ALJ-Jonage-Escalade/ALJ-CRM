<script setup lang="ts">
/* The results poster itself, drawn at its real size (1080 px wide, as tall as its categories) to be turned into a PNG:
   a banner (logo, competition, a volume), the figures, one card per category with a hold in its corner, a footer.
   Colours: posterTheme.ts; the result badges are those of the competition page (palette.ts). */
import { computed } from "vue";
import { SOFT } from "../../../components/ui/palette";
import { periodText, type Competition, type Participant } from "../competitions";
import { posterBlocks, posterSummary } from "./poster";
import PosterArt, { type ArtName } from "./PosterArt.vue";
import { posterThemeStyle } from "./posterTheme";

/* Served by FastAPI next to the PWA files (web/assets), same origin: the PNG can embed it */
const LOGO_URL = "/annuaire/assets/logo.png";
const HOLDS: readonly ArtName[] = ["crimp", "sloper_1", "sloper_2", "sloper_3"];

const props = defineProps<{ competition: Competition; participants: readonly Participant[] }>();

const blocks = computed(() => posterBlocks(props.participants));
const summary = computed(() => posterSummary(blocks.value));
const where = computed(() => [periodText(props.competition), props.competition.lieu].filter(Boolean).join(" · "));
const themeStyle = posterThemeStyle();

/** The hold in the corner of a category's card: the four in turn, each time turned another way (137°, not a multiple
    of 90°), so that they do not look repeated. */
const watermark = (index: number): { name: ArtName; turn: string } => ({
  name: HOLDS[index % HOLDS.length] ?? "crimp",
  turn: `rotate(${(index * 137) % 360}deg)`,
});
</script>

<template>
  <div
    class="w-[1080px] overflow-hidden font-sans"
    :style="[themeStyle, { background: 'linear-gradient(160deg, var(--poster-page-from), var(--poster-page-via), var(--poster-page-to))' }]"
  >
    <header
      class="relative overflow-hidden px-14 pt-12 pb-10"
      style="background: linear-gradient(135deg, var(--poster-banner-from), var(--poster-banner-to))"
    >
      <PosterArt name="volume" class="absolute top-1/2 right-10 h-[200px] w-[200px] -translate-y-1/2 text-(--poster-volume)" />
      <div class="relative flex items-center gap-8 pr-24">
        <div class="shrink-0 rounded-full bg-white p-3 shadow-xl">
          <img :src="LOGO_URL" alt="" class="h-32 w-32 rounded-full object-contain" />
        </div>
        <div class="min-w-0">
          <p class="text-[30px] font-extrabold tracking-[0.3em] text-(--poster-accent) uppercase">Résultats</p>
          <h1 class="text-[52px] leading-tight font-black text-balance text-(--poster-title)">{{ competition.nom }}</h1>
          <p class="mt-1 text-[28px] text-(--poster-muted)">{{ where }}</p>
        </div>
      </div>
    </header>

    <div
      class="flex justify-center gap-14 border-y-2 border-(--poster-band-border) bg-(--poster-band) py-4 text-[30px] font-bold text-(--poster-title)"
    >
      <span>{{ summary.ranked }} {{ summary.ranked > 1 ? "grimpeurs classés" : "grimpeur classé" }}</span>
      <template v-if="summary.podiums">
        <span class="text-(--poster-accent)">•</span>
        <span>🏅 {{ summary.podiums }} {{ summary.podiums > 1 ? "podiums" : "podium" }}</span>
      </template>
    </div>

    <main class="flex flex-col gap-5 px-12 pt-8">
      <section
        v-for="(block, index) in blocks"
        :key="block.title"
        class="relative overflow-hidden rounded-3xl bg-(--poster-card) px-8 py-4 shadow-lg"
      >
        <PosterArt
          :name="watermark(index).name"
          class="absolute -top-10 right-40 h-[200px] w-[200px] text-(--poster-watermark) opacity-(--poster-watermark-opacity)"
          :style="{ transform: watermark(index).turn }"
        />
        <h2 class="relative mb-1 text-[38px] font-black text-(--poster-title)">{{ block.title }}</h2>
        <div
          v-for="(line, row) in block.lines"
          :key="row"
          :class="['relative flex items-center justify-between py-1.5 text-[32px]', row ? 'border-t border-(--poster-card-line)' : '']"
        >
          <span class="min-w-0 font-semibold text-(--poster-name)">{{ line.name }}</span>
          <!-- The result badge of the competition page (UiBadge soft), at the poster's size -->
          <span :class="['shrink-0 rounded-xl border-2 px-4 font-bold whitespace-nowrap', SOFT[line.color]]">{{ line.place }}</span>
        </div>
      </section>
    </main>

    <footer
      class="mt-8 flex items-center justify-between border-t-2 border-(--poster-band-border) bg-(--poster-band) px-14 py-5 text-[28px] font-bold"
    >
      <span class="text-(--poster-title)">ALJ Escalade · Jonage</span>
      <span class="text-(--poster-accent)">Bravo à tous ! 💪</span>
    </footer>
  </div>
</template>
