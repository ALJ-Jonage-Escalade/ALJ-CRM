<script setup lang="ts">
/* Preview of the results poster, then download it (or share it, on a phone that can share files: WhatsApp…). The
   poster is drawn off screen at its real size and turned into a PNG once; the preview is that very image. */
import { domToBlob } from "modern-screenshot";
import { computed, nextTick, onBeforeUnmount, ref, useTemplateRef, watch } from "vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiDialog from "../../../components/ui/UiDialog.vue";
import UiDialogActions from "../../../components/ui/UiDialogActions.vue";
import { useWideLayout } from "../../../composables/media";
import { saveFile } from "../../../lib/download";
import type { Competition, Participant } from "../competitions";
import ResultsPoster from "./ResultsPoster.vue";

const props = defineProps<{ competition: Competition; participants: readonly Participant[] }>();
const open = defineModel<boolean>("open", { required: true });

const wide = useWideLayout();
const poster = useTemplateRef<InstanceType<typeof ResultsPoster>>("poster");
const image = ref<File | null>(null);
const imageUrl = ref("");
const failed = ref(false);

/** « resultats_Coupe_regionale_de_bloc_2026-12-14.png »: accents dropped, the rest of the punctuation as « _ ». */
const fileName = computed(() => {
  const { nom, date_competition } = props.competition;
  const name = (nom || "competition").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\W+/g, "_");
  return `resultats_${[name, date_competition].filter(Boolean).join("_")}.png`;
});

const canShare = computed(
  () => !wide.value && !!image.value && typeof navigator.canShare === "function" && navigator.canShare({ files: [image.value] }),
);

function clear(): void {
  if (imageUrl.value) {
    URL.revokeObjectURL(imageUrl.value);
  }
  image.value = null;
  imageUrl.value = "";
  failed.value = false;
}

async function draw(): Promise<void> {
  clear();
  await nextTick();
  const element = poster.value?.$el;
  if (!(element instanceof HTMLElement)) {
    return;
  }
  try {
    const blob = await domToBlob(element, { type: "image/png", scale: 1 });
    image.value = new File([blob], fileName.value, { type: "image/png" });
    imageUrl.value = URL.createObjectURL(blob);
  } catch {
    failed.value = true;
  }
}

watch(open, (isOpen) => (isOpen ? void draw() : clear()), { immediate: true });
onBeforeUnmount(clear);

function download(): void {
  if (image.value) {
    saveFile(image.value, fileName.value);
  }
}

async function share(): Promise<void> {
  if (!image.value) {
    return;
  }
  try {
    await navigator.share({ files: [image.value], title: `Résultats : ${props.competition.nom ?? ""}` });
  } catch (error) {
    if (!(error instanceof DOMException && error.name === "AbortError")) {
      failed.value = true; // the share sheet closed by the user is not a failure
    }
  }
}
</script>

<template>
  <UiDialog v-model:open="open" title="🖼️ Affiche des résultats" xl data-testid="poster-dialog">
    <p v-if="failed" class="mb-3 text-[13px] text-red-700" data-testid="poster-error">
      ❌ L'affiche n'a pas pu être créée ou partagée. Réessayez, ou téléchargez-la.
    </p>
    <img
      v-if="imageUrl"
      :src="imageUrl"
      alt="Affiche des résultats"
      class="mx-auto max-h-[65dvh] w-auto rounded-lg border border-slate-200"
      data-testid="poster-preview"
    />
    <p v-else-if="!failed" class="py-10 text-center text-[13px] text-slate-500">⏳ Création de l'affiche…</p>
    <UiDialogActions>
      <UiButton v-if="canShare" data-testid="poster-share" @click="share">📤 Partager</UiButton>
      <UiButton :variant="canShare ? 'muted' : undefined" :disabled="!image" data-testid="poster-download" @click="download">
        📥 Télécharger
      </UiButton>
    </UiDialogActions>
  </UiDialog>
  <!-- Off screen at its real size: the PNG is drawn from it -->
  <Teleport v-if="open" to="body">
    <div class="pointer-events-none fixed top-0 -left-[10000px]" aria-hidden="true">
      <ResultsPoster ref="poster" :competition="competition" :participants="participants" />
    </div>
  </Teleport>
</template>
