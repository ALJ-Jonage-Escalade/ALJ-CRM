<script setup lang="ts">
/* Modal dialog of the club theme. Reka UI brings the behaviour: focus kept inside, Escape and a click outside close
   it, the focus goes back to the button that opened it. */
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from "reka-ui";

// Attributes (data-testid…) go to the dialog box, not to the root, which renders nothing
defineOptions({ inheritAttrs: false });
defineProps<{ title: string; description?: string }>();
const open = defineModel<boolean>("open", { required: true });
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-40 bg-slate-900/50" />
      <DialogContent
        class="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl bg-white p-5 shadow-xl"
        v-bind="$attrs"
      >
        <DialogTitle class="mb-3 pr-8 text-[15px] font-bold">{{ title }}</DialogTitle>
        <DialogDescription v-if="description" class="mb-3 text-[13px] text-slate-500">{{ description }}</DialogDescription>
        <slot />
        <!-- After the content: the dialog focuses its first field, not this button -->
        <DialogClose aria-label="Fermer" class="absolute top-4 right-4 cursor-pointer text-xl leading-none text-slate-500 hover:text-slate-800">✕</DialogClose>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
