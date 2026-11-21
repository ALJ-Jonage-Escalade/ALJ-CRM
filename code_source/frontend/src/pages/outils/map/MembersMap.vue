<script setup lang="ts">
/* Map of the members' addresses for a season: markers grouped in clusters, a popup per address and a filter on the
   groups (HelloAsso tariffs). The points come from /api/reports/map-points; Leaflet is loaded on first display. */
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import { computed, inject, onBeforeUnmount, onMounted, ref, shallowRef, useTemplateRef, watch } from "vue";
import UiButton from "../../../components/ui/UiButton.vue";
import { CLIENT_KEY, errorText } from "../../../lib/client";
import { createReportsApi } from "../../../services/reports";
import { filterLabel, groupsOf, mapSummaryText, visiblePoints, type MapPoint } from "./membersMap";
import type { MembersMapView } from "./membersMapView";

const props = defineProps<{ season: string }>();
const reportsApi = createReportsApi(inject(CLIENT_KEY)!);

const container = useTemplateRef<HTMLElement>("container");
const points = shallowRef<MapPoint[]>([]);
const status = ref<"loading" | "ready" | "error">("loading");
const message = ref("");
// Hidden rather than shown groups: a group that appears on a reload is shown
const hidden = ref<ReadonlySet<string>>(new Set());

const groups = computed(() => groupsOf(points.value));
const shownCount = computed(() => groups.value.filter((g) => !hidden.value.has(g)).length);
const visible = computed(() => visiblePoints(points.value, hidden.value));

let view: MembersMapView | null = null;
let unmounted = false;
let request = 0;

async function mapView(): Promise<MembersMapView | null> {
  if (!view) {
    const { createMembersMapView } = await import("./membersMapView");
    if (!unmounted && container.value && !view) {
      view = createMembersMapView(container.value);
    }
  }
  return view;
}

async function load(): Promise<void> {
  const mine = ++request; // a slower answer for a former season is dropped
  status.value = "loading";
  try {
    const [data] = await Promise.all([reportsApi.mapPoints(props.season), mapView()]);
    if (mine !== request) {
      return;
    }
    points.value = data.points;
    status.value = "ready";
  } catch (e) {
    if (mine !== request) {
      return;
    }
    message.value = `❌ Impossible de charger la carte : ${errorText(e)}`;
    status.value = "error";
  }
}

// After the DOM update: the map is measured once visible
watch(visible, (shown) => view?.show(shown), { flush: "post" });

function toggle(group: string, shown: boolean): void {
  const next = new Set(hidden.value);
  if (shown) {
    next.delete(group);
  } else {
    next.add(group);
  }
  hidden.value = next;
}

function toggleAll(shown: boolean): void {
  hidden.value = shown ? new Set() : new Set(groups.value);
}

const checked = (event: Event) => event.target instanceof HTMLInputElement && event.target.checked;

watch(() => props.season, load);
onMounted(load);
onBeforeUnmount(() => {
  unmounted = true;
  request++;
  view?.destroy();
  view = null;
});
</script>

<template>
  <div class="mb-2 flex flex-wrap items-center gap-2">
    <PopoverRoot>
      <PopoverTrigger as-child>
        <UiButton variant="muted" small data-testid="map-groups" :disabled="!groups.length">
          {{ filterLabel(groups.length, shownCount) }} ▾
        </UiButton>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent
          align="start"
          :side-offset="4"
          class="z-50 max-h-96 w-64 overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
        >
          <label class="flex cursor-pointer items-center gap-2 border-b border-slate-100 px-3 py-2 text-[13px] font-bold hover:bg-slate-50">
            <input
              type="checkbox"
              data-testid="map-group-all"
              :checked="shownCount === groups.length"
              :indeterminate="shownCount > 0 && shownCount < groups.length"
              @change="toggleAll(checked($event))"
            />
            🧗 Sélectionner tout
          </label>
          <label
            v-for="group in groups"
            :key="group"
            class="flex cursor-pointer items-center gap-2 border-b border-slate-100 px-3 py-2 text-[13px] last:border-b-0 hover:bg-slate-50"
          >
            <input
              type="checkbox"
              data-testid="map-group"
              :value="group"
              :checked="!hidden.has(group)"
              @change="toggle(group, checked($event))"
            />
            {{ group }}
          </label>
        </PopoverContent>
      </PopoverPortal>
    </PopoverRoot>
    <span v-if="status === 'ready'" data-testid="map-stats" class="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">
      {{ mapSummaryText(visible, groups.length, shownCount) }}
    </span>
  </div>
  <div
    v-if="status !== 'ready'"
    data-testid="map-status"
    :class="[
      'mb-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px]',
      status === 'error' ? 'text-red-600' : 'text-slate-500',
    ]"
  >
    {{ status === "loading" ? "⏳ Chargement de la carte géographique des adhérents…" : message }}
  </div>
  <!-- isolate: Leaflet's panes and controls (z-index 400 to 1000) stay below the app's menus and dialogs -->
  <div
    ref="container"
    data-testid="map-view"
    class="isolate h-[calc(100dvh-16rem)] min-h-[420px] w-full rounded-xl border border-slate-200 bg-white"
  />
</template>
