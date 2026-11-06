<script setup lang="ts">
/* A competitor of the competition. */
import UiBadge from "../../../components/ui/UiBadge.vue";
import { telHref } from "../../../lib/text";
import { hasPaid, isCancelled, paymentBadge, rankingText, type Row } from "../competitions";

const props = defineProps<{ row: Row; canWrite: boolean; staff: boolean; contactsShown: boolean }>();
const emit = defineEmits<{
  toggle: [flag: "selectionne" | "present", value: boolean];
  remove: [];
  pay: [];
  withdraw: [];
  restore: [];
  showContact: [];
}>();

/* The box shows the data, not the click: it changes once the change is made (or queued), and stays put when refused. */
function onToggle(flag: "selectionne" | "present", e: Event): void {
  const box = e.target as HTMLInputElement;
  const value = box.checked;
  box.checked = !!props.row[flag];
  emit("toggle", flag, value);
}

const telButton = "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11.5px] font-semibold no-underline";
const action = "cursor-pointer rounded-md border bg-white px-2 py-0.5 text-[11.5px] font-bold";
</script>

<template>
  <li data-testid="participant-card" class="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 shadow-sm">
    <div class="flex items-start justify-between gap-2">
      <span class="min-w-0">
        <button
          v-if="contactsShown"
          type="button"
          data-testid="participant-name"
          class="block cursor-pointer text-left text-[14.5px] font-bold text-blue-950 hover:text-blue-600 hover:underline"
          title="Voir la fiche contact"
          @click="emit('showContact')"
        >
          {{ row.nom }} {{ row.prenom }}
        </button>
        <b v-else class="block text-[14.5px]" data-testid="participant-name">{{ row.nom }} {{ row.prenom }}</b>
        <span class="block text-xs text-slate-500">
          🪪 {{ row.num_licence || "sans licence" }} · {{ row.tarif || "—" }}
          <template v-if="staff && row.commande_helloasso">· 🧾 {{ row.commande_helloasso }}</template>
          <template v-if="staff && row.note_paiement">· 📝 {{ row.note_paiement }}</template>
        </span>
      </span>
      <UiBadge :color="paymentBadge(row.statut_paiement).color" class="shrink-0" data-testid="payment-badge" title="Statut de paiement">
        {{ paymentBadge(row.statut_paiement).label }}
        <template v-if="row.montant_paye">({{ row.montant_paye }} €)</template>
      </UiBadge>
    </div>

    <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
      <label
        v-if="canWrite"
        :class="[
          'inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-0.5 text-[11.5px] font-bold',
          row.selectionne ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-500',
        ]"
      >
        <input
          type="checkbox"
          role="switch"
          data-testid="participe-switch"
          class="size-4 accent-blue-600"
          :checked="row.selectionne"
          @change="onToggle('selectionne', $event)"
        />
        Participe
      </label>
      <UiBadge v-else :color="row.selectionne ? 'blue' : 'slate'" variant="soft" data-testid="participe">
        {{ row.selectionne ? "✅ Participe" : "— Ne participe pas" }}
      </UiBadge>
      <label
        v-if="canWrite"
        :class="[
          'inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-0.5 text-[11.5px] font-bold',
          row.present ? 'bg-green-50 text-green-700' : 'bg-slate-100 text-slate-500',
        ]"
      >
        <input
          type="checkbox"
          data-testid="present-switch"
          class="size-4 accent-green-600"
          :checked="row.present"
          @change="onToggle('present', $event)"
        />
        Présent
      </label>
      <span
        v-if="row.queued.selectionne || row.queued.present"
        data-testid="queued"
        title="Modifié hors ligne : sera envoyé au retour du réseau"
        class="text-[11px] font-bold text-amber-700"
      >
        ⏳ à envoyer
      </span>
      <UiBadge v-if="rankingText(row)" color="amber" variant="soft" data-testid="ranking">
        {{ rankingText(row) }}
        <template v-if="row.categorie_ffme">· {{ row.categorie_ffme }}</template>
      </UiBadge>
      <template v-if="contactsShown">
        <a v-if="row.phone" :href="telHref(row.phone)" :class="[telButton, 'border-blue-200 bg-blue-50 text-blue-700']">
          📞 {{ row.phone }}
        </a>
        <a
          v-for="(e, position) in row.emergency"
          :key="position"
          :href="telHref(e.phone)"
          title="Contact d'urgence"
          data-testid="emergency-link"
          :class="[telButton, 'border-red-200 bg-red-50 text-red-700']"
        >
          🚨 {{ e.name || "Urgence" }} · {{ e.phone }}
        </a>
      </template>
    </div>

    <div v-if="canWrite" class="mt-1.5 flex flex-wrap gap-1.5" data-testid="participant-actions">
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
          title="Retirer de l'épreuve (aucun paiement reçu)"
          @click="emit('remove')"
        >
          ✕ Retirer
        </button>
        <button
          type="button"
          data-testid="manual-payment"
          :class="[action, 'border-green-200 text-green-700 hover:bg-green-50']"
          title="Paiement reçu par chèque ou en espèces"
          @click="emit('pay')"
        >
          💶 Paiement manuel
        </button>
      </template>
    </div>
  </li>
</template>
