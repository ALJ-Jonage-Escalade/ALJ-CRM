<script setup lang="ts">
/* One action of a UiMenu. danger: a destructive action (red, after a separator line). */
import { DropdownMenuItem, DropdownMenuSeparator } from "reka-ui";

// Attributes (data-testid…) go to the item, not to the separator before it
defineOptions({ inheritAttrs: false });
withDefaults(defineProps<{ danger?: boolean; disabled?: boolean }>(), { danger: false, disabled: false });
const emit = defineEmits<{ select: [] }>();
</script>

<template>
  <DropdownMenuSeparator v-if="danger" class="my-1 h-px bg-slate-100" />
  <DropdownMenuItem
    :disabled="disabled"
    :class="[
      'block cursor-pointer px-3 py-2 text-[12.5px] outline-none data-disabled:cursor-not-allowed data-disabled:opacity-50',
      danger ? 'text-red-600 data-highlighted:bg-red-50' : 'text-slate-700 data-highlighted:bg-slate-100',
    ]"
    v-bind="$attrs"
    @select="emit('select')"
  >
    <slot />
  </DropdownMenuItem>
</template>
