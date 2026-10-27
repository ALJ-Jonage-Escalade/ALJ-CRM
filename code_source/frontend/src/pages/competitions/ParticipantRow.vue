<script setup lang="ts">
/* A competitor as a row of the wide-screen table (the former desktop page); ParticipantCard elsewhere. Same test ids,
   events and rules as the card: « Participe » and « Présent » switches, then the action allowed by the payment. */
import UiBadge from "../../components/ui/UiBadge.vue";
import { telHref } from "../adherents/members";
import { hasPaid, isCancelled, payment, ranking, type Row } from "./competitions";

const props = defineProps<{ row: Row; canWrite: boolean; staff: boolean; contactsShown: boolean }>();
const emit = defineEmits<{ toggle: [flag: "selectionne" | "present", value: boolean]; remove: []; pay: []; withdraw: []; restore: [] }>();

/* The box shows the data, not the click: it changes once the change is made (or queued), and stays put when refused. */
function onToggle(flag: "selectionne" | "present", e: Event): void {
  const box = e.target as HTMLInputElement;
  const value = box.checked;
  box.checked = !!props.row[flag];
  emit("toggle", flag, value);
}

const telLink = "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11.5px] font-semibold whitespace-nowrap no-underline";
const action = "cursor-pointer rounded-md border bg-white px-2 py-0.5 text-[11.5px] font-bold whitespace-nowrap";
</script>

<template>
  <tr data-testid="participant-card" class="border-t border-slate-100 align-middle hover:bg-slate-50">
    <td class="px-2.5 py-2">
      <b class="block text-[13.5px] whitespace-nowrap" data-testid="participant-name">{{ row.nom }} {{ row.prenom }}</b>
      <span class="block text-[11px] text-slate-500">
        🪪 {{ row.num_licence || "sans licence" }}
        <template v-if="staff && row.commande_helloasso">· 🧾 {{ row.commande_helloasso }}</template>
        <template v-if="staff && row.note_paiement">· 📝 {{ row.note_paiement }}</template>
      </span>
    </td>
    <td class="px-2.5 py-2 text-center">
      <UiBadge v-if="ranking(row)" color="amber" variant="soft" data-testid="ranking">{{ ranking(row) }}</UiBadge>
      <span v-else class="text-xs text-slate-400">—</span>
      <span v-if="ranking(row) && row.categorie_ffme" class="block text-[10.5px] text-slate-500">{{ row.categorie_ffme }}</span>
    </td>
    <td class="px-2.5 py-2 text-center">
      <input
        v-if="canWrite"
        type="checkbox"
        role="switch"
        data-testid="participe-switch"
        aria-label="Participe"
        class="size-4 cursor-pointer accent-blue-600"
        :checked="row.selectionne"
        @change="onToggle('selectionne', $event)"
      />
      <span v-else data-testid="participe" class="text-xs font-bold" :class="row.selectionne ? 'text-blue-700' : 'text-slate-400'">
        {{ row.selectionne ? "✅ Oui" : "—" }}
      </span>
    </td>
    <td class="px-2.5 py-2">
      <UiBadge :color="payment(row.statut_paiement).color" data-testid="payment-badge" title="Statut de paiement">
        {{ payment(row.statut_paiement).label }}
        <template v-if="row.montant_paye">({{ row.montant_paye }} €)</template>
      </UiBadge>
    </td>
    <td class="px-2.5 py-2 text-center">
      <input
        v-if="canWrite"
        type="checkbox"
        data-testid="present-switch"
        aria-label="Présent"
        class="size-4.5 cursor-pointer accent-green-600"
        :checked="row.present"
        @change="onToggle('present', $event)"
      />
      <span v-else class="text-xs font-bold" :class="row.present ? 'text-green-700' : 'text-slate-400'">{{ row.present ? "✓" : "—" }}</span>
      <span
        v-if="row.queued.selectionne || row.queued.present"
        data-testid="queued"
        title="Modifié hors ligne : sera envoyé au retour du réseau"
        class="block text-[10.5px] font-bold whitespace-nowrap text-amber-700"
      >
        ⏳ à envoyer
      </span>
    </td>
    <td class="px-2.5 py-2">
      <div v-if="contactsShown && (row.phone || row.emergency.length)" class="flex flex-col items-start gap-1">
        <a v-if="row.phone" :href="telHref(row.phone)" :class="[telLink, 'border-blue-200 bg-blue-50 text-blue-700']">📞 {{ row.phone }}</a>
      </div>
      <span v-else class="text-xs text-slate-400">—</span>
    </td>
    <td v-if="canWrite" class="px-2.5 py-2 text-center">
      <div class="inline-flex flex-wrap justify-center gap-1" data-testid="participant-actions">
        <UiBadge
          v-if="row.present"
          color="green"
          variant="soft"
          data-testid="on-site"
          title="Pointé présent : décochez « Présent » après une erreur pour retrouver les actions"
        >
          ✓ Sur place
        </UiBadge>
        <button
          v-else-if="hasPaid(row)"
          type="button"
          data-testid="withdraw"
          :class="[action, 'border-violet-200 text-violet-700 hover:bg-violet-50']"
          title="Paiement reçu : pas de retrait, un désistement (report ou perte)"
          @click="emit('withdraw')"
        >
          🔒 Désister…
        </button>
        <button
          v-else-if="isCancelled(row)"
          type="button"
          data-testid="restore"
          :class="[action, 'border-blue-200 text-blue-700 hover:bg-blue-50']"
          @click="emit('restore')"
        >
          ↩️ Rétablir
        </button>
        <template v-else>
          <button
            type="button"
            data-testid="remove"
            :class="[action, 'border-red-200 text-red-600 hover:bg-red-50']"
            title="Supprimer ce compétiteur de la compétition"
            @click="emit('remove')"
          >
            🗑️ Supprimer
          </button>
          <button
            type="button"
            data-testid="manual-payment"
            :class="[action, 'border-green-200 text-green-700 hover:bg-green-50']"
            title="Paiement reçu par chèque ou en espèces"
            @click="emit('pay')"
          >
            💶
          </button>
        </template>
      </div>
    </td>
  </tr>
</template>
