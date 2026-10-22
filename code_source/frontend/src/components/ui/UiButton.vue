<script setup lang="ts">
/* Button of the club theme. busy: disabled, with the given label instead of the slot (an action in progress). */
withDefaults(
  defineProps<{ variant?: "primary" | "muted" | "warning"; small?: boolean; busy?: string | false; disabled?: boolean; type?: "button" | "submit" }>(),
  { variant: "primary", small: false, busy: false, disabled: false, type: "button" },
);
</script>

<template>
  <button
    :type="type"
    :disabled="!!busy || disabled"
    :class="[
      'inline-flex cursor-pointer items-center gap-1.5 rounded-lg font-bold disabled:cursor-wait disabled:opacity-60',
      small ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-[13px]',
      variant === 'primary' && 'bg-accent text-white hover:bg-accent-dark',
      variant === 'muted' && 'bg-slate-200 text-slate-700 hover:bg-slate-300',
      variant === 'warning' && 'border border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100',
    ]"
  >
    <template v-if="busy">⏳ {{ busy }}</template>
    <slot v-else />
  </button>
</template>
