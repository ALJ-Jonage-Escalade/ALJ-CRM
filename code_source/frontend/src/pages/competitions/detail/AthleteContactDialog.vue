<script setup lang="ts">
/* Modal displaying the complete contact card of an athlete in a competition: the athlete themselves, emergency contact 1 and emergency contact 2. */
import UiBadge from "../../../components/ui/UiBadge.vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiDialog from "../../../components/ui/UiDialog.vue";
import UiDialogActions from "../../../components/ui/UiDialogActions.vue";
import { telHref } from "../../adherents/members";
import type { Row } from "../competitions";

defineProps<{
  athlete: Row | null;
  open: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
}>();
</script>

<template>
  <UiDialog
    :open="open"
    :title="athlete ? `📇 Fiche contact : ${athlete.prenom} ${athlete.nom}` : '📇 Fiche contact'"
    description="Coordonnées de l'athlète et de ses contacts d'urgence"
    wide
    data-testid="athlete-contact-dialog"
    @update:open="emit('update:open', $event)"
  >
    <div v-if="athlete" class="flex flex-col gap-4">
      <!-- En-tête résumé athlète -->
      <div class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-700">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-bold">🪪 {{ athlete.num_licence || "Sans licence" }}</span>
          <span>·</span>
          <span>🧗 {{ athlete.group || athlete.tarif || "Groupe non renseigné" }}</span>
          <template v-if="athlete.categorie_ffme">
            <span>·</span>
            <span>🏅 Catégorie {{ athlete.categorie_ffme }}</span>
          </template>
        </div>
        <UiBadge v-if="athlete.statut_paiement" color="blue" variant="soft">
          {{ athlete.selectionne ? "Participe" : "Non invité" }}
        </UiBadge>
      </div>

      <!-- Les 3 fiches de contact -->
      <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div
          v-for="c in athlete.contacts"
          :key="c.role"
          data-testid="contact-card"
          class="flex flex-col justify-between rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 shadow-sm"
        >
          <div class="flex flex-col gap-2">
            <div class="flex items-center justify-between border-b border-slate-200/80 pb-2">
              <span class="text-xs font-black tracking-wide text-slate-800 uppercase" data-testid="contact-title">{{ c.title }}</span>
            </div>

            <div class="text-sm font-bold text-slate-900" data-testid="contact-name">
              {{ c.name || "—" }}
            </div>

            <div class="flex flex-col gap-1.5 text-xs">
              <div class="flex items-start gap-1.5">
                <span class="w-16 shrink-0 text-slate-500">Téléphone :</span>
                <a
                  v-if="c.phone"
                  :href="telHref(c.phone)"
                  data-testid="contact-phone-link"
                  class="font-semibold text-blue-700 hover:underline"
                >
                  📞 {{ c.phone }}
                </a>
                <span v-else class="text-slate-400 italic">Non renseigné</span>
              </div>

              <div v-if="c.role === 'athlete'" class="flex items-start gap-1.5">
                <span class="w-16 shrink-0 text-slate-500">Email :</span>
                <a
                  v-if="c.email"
                  :href="'mailto:' + c.email"
                  data-testid="contact-email-link"
                  class="truncate font-semibold text-blue-700 hover:underline"
                  :title="c.email"
                >
                  ✉️ {{ c.email }}
                </a>
                <span v-else class="text-slate-400 italic">Non renseigné</span>
              </div>
            </div>
          </div>

          <!-- Raccourcis d'action -->
          <div v-if="c.phone || c.email" class="mt-3 flex flex-wrap gap-1.5 border-t border-slate-200/80 pt-2.5">
            <a
              v-if="c.phone"
              :href="telHref(c.phone)"
              class="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-bold text-blue-700 no-underline hover:bg-blue-100"
            >
              📞 Appeler
            </a>
            <a
              v-if="c.email"
              :href="'mailto:' + c.email"
              class="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-700 no-underline hover:bg-slate-100"
            >
              ✉️ Écrire
            </a>
          </div>
        </div>
      </div>
    </div>

    <UiDialogActions class="mt-4">
      <UiButton variant="muted" data-testid="close-contact-dialog" @click="emit('update:open', false)">Fermer</UiButton>
    </UiDialogActions>
  </UiDialog>
</template>
