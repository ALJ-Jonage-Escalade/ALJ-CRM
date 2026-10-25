<script setup lang="ts">
/* The e-mail as the demo member would receive it. The body is shown as text: the HTML tags stay visible. */
import { PREVIEW_TO, type Preview } from "./editor";

defineProps<{ preview: Preview; signature: boolean }>();
</script>

<template>
  <div class="rounded-lg border border-slate-300 bg-white p-4 text-[13px] shadow-sm">
    <div class="mb-3 flex flex-col gap-1 border-b border-slate-200 pb-2.5 text-xs text-slate-500">
      <div>
        <b class="text-slate-800">De :</b>
        <span data-testid="preview-from">{{ preview.from }}</span>
      </div>
      <div>
        <b class="text-slate-800">À :</b>
        {{ PREVIEW_TO }}
      </div>
      <div>
        <b class="text-slate-800">Objet :</b>
        <span data-testid="preview-subject" class="font-bold text-club-blue">{{ preview.subject }}</span>
      </div>
    </div>
    <div data-testid="preview-body" class="leading-relaxed break-words whitespace-pre-wrap">{{ preview.body }}</div>
    <div
      v-if="signature"
      data-testid="preview-signature"
      class="mt-4 flex items-center gap-3 border-t border-slate-200 pt-3 text-xs text-slate-600"
    >
      <div class="text-2xl" aria-hidden="true">🧗</div>
      <div>
        <b class="text-[13px] text-club-blue">Amicale Laïque de Jonage — Section Escalade</b>
        <br />
        <span class="text-[11px] text-slate-500">Mairie de Jonage · 69330 Jonage</span>
        <br />
        <span class="text-[11px] text-blue-500">Suivez-nous sur Instagram & Facebook</span>
      </div>
    </div>
  </div>
</template>
