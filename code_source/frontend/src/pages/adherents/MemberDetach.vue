<script setup lang="ts">
/* Detaching a membership from HelloAsso (admins, #84): a registration of the import given to the wrong member. The
   membership is deleted (no restore), the member record is not changed; the next HelloAsso import sees the registration
   again, to attach it to the right member. The reason is required: the server keeps it in the import history. */
import { computed, inject, ref } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiDialogActions from "../../components/ui/UiDialogActions.vue";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createMembersApi } from "../../services/members";
import type { Member } from "./members";

const props = defineProps<{ member: Member }>();
const emit = defineEmits<{ detached: [message: string]; failed: [message: string]; cancel: [] }>();
const membersApi = createMembersApi(inject(CLIENT_KEY)!);

const reason = ref("");
const sending = ref(false);
const name = computed(() => `${props.member.first_name} ${props.member.last_name}`);

async function detach(): Promise<void> {
  sending.value = true;
  try {
    const detached = await membersApi.detachHelloAsso(props.member.purchase_id, reason.value.trim());
    emit(
      "detached",
      `🔗 Inscription HelloAsso (commande ${detached.order_ref}) détachée de ${name.value} : adhésion ${detached.season} supprimée. ` +
        "Rattachez-la au bon adhérent depuis Outils › Import HelloAsso.",
    );
  } catch (e) {
    emit("failed", `❌ Échec du détachement : ${errorText(e)}`);
  } finally {
    sending.value = false;
  }
}
</script>

<template>
  <form class="flex flex-col gap-3 text-[13px]" data-testid="detach-form" @submit.prevent="reason.trim() && detach()">
    <p>
      Détacher l'inscription HelloAsso (commande {{ member.order_ref }}, {{ member.tarif_name || "sans tarif" }}, saison
      {{ member.season_name }}) de
      <strong>{{ name }}</strong>
      ?
    </p>
    <ul class="list-disc pl-5 text-slate-600">
      <li>
        L'adhésion {{ member.season_name }} et ses options d'assurance sont
        <strong>supprimées</strong>
        , sans retour arrière.
      </li>
      <li>La fiche de l'adhérent n'est pas modifiée.</li>
      <li>Une licence déjà transmise à la FFME n'y est pas annulée.</li>
      <li>Au prochain import HelloAsso, l'inscription réapparaît : rattachez-la au bon adhérent.</li>
    </ul>
    <label for="detach-reason" class="font-semibold text-slate-700">Raison (gardée dans l'historique des imports)</label>
    <textarea
      id="detach-reason"
      v-model="reason"
      data-testid="detach-reason"
      rows="3"
      required
      placeholder="Inscription au nom de la mère, rattachée au mauvais enfant…"
      class="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5"
    />
    <UiDialogActions>
      <UiButton variant="muted" @click="emit('cancel')">Annuler</UiButton>
      <UiButton type="submit" variant="danger" data-testid="detach-confirm" :disabled="!reason.trim()" :busy="sending && 'Détachement…'">
        🔗 Détacher et supprimer l'adhésion
      </UiButton>
    </UiDialogActions>
  </form>
</template>
