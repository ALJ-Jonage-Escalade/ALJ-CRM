<script setup lang="ts">
/* Collapsible panel next to a list (the member record beside the Adhérents table). From lg up it is a column of its
   own, sticky while the page scrolls, with its own scroll bar; below, it stacks above the list. Collapsed, it is not
   rendered at all: the page shows a button to open it again (aria-controls: the panel's id). */
defineOptions({ inheritAttrs: false });
defineProps<{ title: string; id: string }>();
const open = defineModel<boolean>("open", { required: true });
</script>

<template>
  <Transition
    enter-active-class="transition duration-150 ease-out"
    enter-from-class="translate-x-3 opacity-0"
    leave-active-class="transition duration-100 ease-in"
    leave-to-class="translate-x-3 opacity-0"
  >
    <aside
      v-if="open"
      :id="id"
      :aria-label="title"
      class="flex flex-col rounded-xl border border-slate-200 bg-white shadow-sm lg:sticky lg:top-4 lg:max-h-[calc(100dvh-2rem)] lg:w-[360px] lg:shrink-0"
      v-bind="$attrs"
    >
      <header class="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5">
        <h2 class="text-[13px] font-bold text-slate-700">{{ title }}</h2>
        <button
          type="button"
          aria-label="Masquer la fiche"
          title="Masquer la fiche"
          :aria-controls="id"
          aria-expanded="true"
          data-testid="side-panel-collapse"
          class="cursor-pointer rounded-md px-1.5 py-0.5 text-base leading-none text-slate-500 hover:bg-slate-100 hover:text-slate-800"
          @click="open = false"
        >
          ⇥
        </button>
      </header>
      <div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        <slot />
      </div>
    </aside>
  </Transition>
</template>
