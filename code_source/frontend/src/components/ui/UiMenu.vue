<script setup lang="ts">
/* Drop-down menu of the club theme: a button that opens a list of UiMenuItem, to tuck away the actions rarely needed.
   Reka UI brings the behaviour: arrow keys move between the items, Escape and a click outside close it, the focus
   goes back to the button. busy: the button shows that one of its actions is in progress (see UiButton). */
import { DropdownMenuContent, DropdownMenuPortal, DropdownMenuRoot, DropdownMenuTrigger } from "reka-ui";
import UiButton from "./UiButton.vue";

// Attributes (data-testid, aria-label…) go to the button, not to the root, which renders nothing
defineOptions({ inheritAttrs: false });
withDefaults(defineProps<{ label: string; small?: boolean; busy?: string | false; align?: "start" | "end" }>(), {
  small: false,
  busy: false,
  align: "end",
});
</script>

<template>
  <DropdownMenuRoot>
    <DropdownMenuTrigger as-child>
      <UiButton variant="muted" :small="small" :busy="busy" v-bind="$attrs">{{ label }} ▾</UiButton>
    </DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent
        :align="align"
        :side-offset="4"
        class="z-50 min-w-52 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
      >
        <slot />
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>
