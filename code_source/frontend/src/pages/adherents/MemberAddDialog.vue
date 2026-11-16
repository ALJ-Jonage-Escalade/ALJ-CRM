<script setup lang="ts">
/* The add form of Adhérents (admins), in a dialog: a member typed by hand for the season shown. Asks before creating a
   member whose name the season already has; the page selects the new member once the list has it (created). */
import { inject, ref, watch } from "vue";
import UiDialog from "../../components/ui/UiDialog.vue";
import { dialogs } from "../../composables/dialogs";
import { CLIENT_KEY, errorText } from "../../lib/client";
import { createMembersApi } from "../../services/members";
import MemberForm from "./MemberForm.vue";
import type { Member } from "./members";
import { draftOf, newMemberOf, sameName, type MemberDraft, type TarifChoice } from "./record";

const open = defineModel<boolean>("open", { required: true });
const props = defineProps<{ season: string; members: readonly Member[]; tarifs: readonly TarifChoice[] }>();
const emit = defineEmits<{
  /** The order of the new membership, to select it once the list is read again. */
  created: [orderRef: string];
  notify: [message: string, ms?: number];
}>();

const membersApi = createMembersApi(inject(CLIENT_KEY)!);
const draft = ref<MemberDraft>(draftOf());
const saving = ref(false);

watch(
  open,
  (now) => {
    if (now) {
      draft.value = draftOf(undefined, props.tarifs[0]?.tarif ?? "");
    }
  },
  { immediate: true },
);
// Tariffs arrive with the list: the first one is chosen when the form opened before
watch(
  () => props.tarifs,
  (now) => {
    if (open.value && !draft.value.tarif_name && now[0]) {
      draft.value.tarif_name = now[0].tarif;
    }
  },
);

async function save(): Promise<void> {
  const twin = sameName(props.members, draft.value);
  if (
    twin &&
    !(await dialogs.confirm({
      title: "Adhérent déjà existant",
      message: `Un adhérent « ${twin.last_name} ${twin.first_name} » existe déjà pour la saison ${props.season}.\n\nVoulez-vous quand même créer cette nouvelle fiche ?`,
      confirmLabel: "Créer quand même",
      variant: "warning",
    }))
  ) {
    return;
  }
  saving.value = true;
  try {
    const created = await membersApi.create({ season: props.season, fields: newMemberOf(draft.value) });
    emit("notify", `✅ ${created.message}`);
    emit("created", created.order_ref);
  } catch (e) {
    emit("notify", `❌ Échec de la création : ${errorText(e)}`, 9000);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <UiDialog
    v-model:open="open"
    title="➕ Ajouter un adhérent"
    :description="`Saisie manuelle d'un adhérent pour la saison ${season}. Les champs marqués d'un astérisque (*) sont obligatoires.`"
    wide
    data-testid="add-dialog"
  >
    <MemberForm v-model="draft" adding :tarifs="tarifs" :saving="saving" @save="save" @cancel="open = false" />
  </UiDialog>
</template>
