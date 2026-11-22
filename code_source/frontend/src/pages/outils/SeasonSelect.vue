<script setup lang="ts">
/* Season read by a tool of the Outils page (map, statistics): one of the seasons, or every season (allSeasons). */
withDefaults(defineProps<{ seasons: string[]; label: string; testid: string; allSeasons?: boolean }>(), { allSeasons: true });
const season = defineModel<string>({ required: true });

/** Understood by the server as every season (MemberRepository.load_direct_data). */
const ALL_SEASONS = "Toutes les saisons";
</script>

<template>
  <label class="flex items-center gap-2 text-[12.5px] font-semibold text-slate-500">
    {{ label }}
    <select
      v-model="season"
      class="rounded-md border border-slate-300 bg-white px-2 py-1 text-[12.5px] text-slate-800"
      :data-testid="testid"
    >
      <option v-for="s in seasons" :key="s" :value="s">{{ s }}</option>
      <option v-if="allSeasons" :value="ALL_SEASONS">{{ ALL_SEASONS }}</option>
    </select>
  </label>
</template>
