<script setup lang="ts">
/* Sub-menu of an office page (plans/sub-menus.md): nested under the page in the desktop side menu, a strip of chips
   under the title on phones (none on Compétitions, which keeps its main page there). AppShell draws both and hides one
   by screen width. A disabled entry stays listed (online
   only, offline): the menu keeps its shape when the network drops. */
import PageLink from "./PageLink.vue";

export interface SubNavItem {
  id: string;
  label: string;
  href: string;
  disabled: boolean;
}

const props = defineProps<{ items: SubNavItem[]; current: string | undefined; variant: "side" | "strip" }>();

const OFFLINE_HINT = "📴 En ligne uniquement";

function itemClass(item: SubNavItem): string[] {
  const active = item.id === props.current;
  if (props.variant === "side") {
    return [
      "rounded-lg py-2 pr-3 pl-9 text-[13px] font-semibold no-underline",
      item.disabled
        ? "cursor-not-allowed text-slate-500"
        : active
          ? "bg-accent text-white"
          : "text-side-text hover:bg-side-hover hover:text-white",
    ];
  }
  return [
    "shrink-0 rounded-lg px-3 py-1.5 text-[13px] font-bold no-underline",
    item.disabled
      ? "cursor-not-allowed border border-slate-200 bg-slate-100 text-slate-400"
      : active
        ? "bg-accent text-white"
        : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
  ];
}
</script>

<template>
  <!-- Inside the main navigation on desktop; its own navigation on phones -->
  <component
    :is="variant === 'strip' ? 'nav' : 'div'"
    :data-testid="`subnav-${variant}`"
    :class="variant === 'side' ? 'flex-col gap-0.5' : 'gap-1.5 overflow-x-auto'"
    :aria-label="variant === 'strip' ? 'Sous-menu' : undefined"
  >
    <template v-for="item in items" :key="item.id">
      <span
        v-if="item.disabled"
        aria-disabled="true"
        :title="OFFLINE_HINT"
        :data-testid="`sub-${variant}-${item.id}`"
        :class="itemClass(item)"
      >
        {{ item.label }}
        <span class="sr-only">({{ OFFLINE_HINT }})</span>
        <span aria-hidden="true">📴</span>
      </span>
      <PageLink
        v-else
        :href="item.href"
        :data-testid="`sub-${variant}-${item.id}`"
        :aria-current="item.id === current ? 'page' : undefined"
        :class="itemClass(item)"
      >
        {{ item.label }}
      </PageLink>
    </template>
  </component>
</template>
