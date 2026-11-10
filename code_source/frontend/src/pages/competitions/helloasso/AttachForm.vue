<script setup lang="ts">
/* A HelloAsso payment: what HelloAsso sent, and the coach's decision. Linked to a competition and a member, it pays for
   that participant (the server selects the member and records the payment); a line unrelated to a competition is
   ignored, with a reason. The competition and member are suggested from what the payer typed. */
import { computed, ref } from "vue";
import UiButton from "../../../components/ui/UiButton.vue";
import UiDialogActions from "../../../components/ui/UiDialogActions.vue";
import { formatDateTime, formatEuros, parseDate } from "../../../lib/format";
import { byName, isArchived, sortCompetitions, type Competition, type MemberSlot } from "../competitions";
import {
  displayName,
  isIgnored,
  isLinked,
  itemInfo,
  stateLabel,
  suggestedCompetition,
  suggestedMember,
  type HelloAssoItem,
} from "./helloasso";

// skippable: in a linking pass, « Passer » goes to the next payment without saving this one
const props = defineProps<{
  item: HelloAssoItem;
  competitions: readonly Competition[];
  members: readonly MemberSlot[];
  busy: boolean;
  skippable?: boolean;
}>();
const emit = defineEmits<{
  link: [competitionId: number | null, adherentId: number | null, comment: string];
  ignore: [ignore: boolean, note: string];
  cancel: [];
  skip: [];
}>();

const info = computed(() => itemInfo(props.item));
const ignored = computed(() => isIgnored(props.item));
const linked = computed(() => isLinked(props.item));
const competitionId = ref<number | null>(suggestedCompetition(props.item, props.competitions));
const adherentId = ref<number | null>(suggestedMember(props.item, props.members));
const comment = ref((ignored.value ? props.item.ignore_motif || props.item.commentaire : props.item.commentaire) ?? "");
const missingReason = ref(false);

const current = computed(() => sortCompetitions(props.competitions).filter((c) => !isArchived(c)));
const archived = computed(() => sortCompetitions(props.competitions).filter(isArchived));
const members = computed(() => props.members.slice().sort(byName));
function when(text: string): string {
  const date = parseDate(text);
  return date ? formatDateTime(date) : text;
}

function ignore(): void {
  missingReason.value = !ignored.value && !comment.value.trim();
  if (!missingReason.value) {
    emit("ignore", !ignored.value, comment.value.trim());
  }
}

const label = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
const field = "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-[13px]";
const th = "py-1 pr-3 align-top text-left font-semibold whitespace-nowrap text-slate-500";
</script>

<template>
  <form
    novalidate
    class="flex flex-col gap-3"
    data-testid="attach-form"
    @submit.prevent="emit('link', competitionId, adherentId, comment.trim())"
  >
    <div class="flex items-baseline justify-between gap-2">
      <b class="text-[15px]" data-testid="attach-name">{{ displayName(item, info) }}</b>
      <b class="text-[15px] text-accent">{{ formatEuros(item.montant) }}</b>
    </div>
    <p v-if="ignored" class="rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-xs" data-testid="attach-ignored">
      🚫
      <b>Ligne ignorée</b>
      <template v-if="item.ignored_by">par {{ item.ignored_by }}</template>
      <template v-if="item.ignored_at">le {{ when(item.ignored_at) }}</template>
      <template v-if="item.ignore_motif">
        <br />
        Motif :
        <i>{{ item.ignore_motif }}</i>
      </template>
    </p>
    <table class="w-full text-xs">
      <tbody>
        <tr v-if="info.itemName">
          <th :class="th">🛒 Article</th>
          <td>{{ info.itemName }}</td>
        </tr>
        <tr v-if="info.formName">
          <th :class="th">📝 Formulaire</th>
          <td>{{ info.formName }}</td>
        </tr>
        <tr v-if="info.orderId">
          <th :class="th">🧾 Commande</th>
          <td>#{{ info.orderId }}</td>
        </tr>
        <tr v-if="info.date">
          <th :class="th">📅 Date</th>
          <td>{{ when(info.date) }}</td>
        </tr>
        <tr v-if="info.payerName || info.payerEmail">
          <th :class="th">💳 Payeur</th>
          <td>
            {{ info.payerName }}
            <template v-if="info.payerEmail">
              ·
              <a :href="`mailto:${info.payerEmail}`">{{ info.payerEmail }}</a>
            </template>
            <template v-if="info.payerCity">· {{ info.payerCity }}</template>
          </td>
        </tr>
        <tr v-if="info.state">
          <th :class="th">📌 État</th>
          <td>{{ stateLabel(info.state) }}</td>
        </tr>
        <tr v-for="(p, i) in info.payments" :key="`p${i}`">
          <th :class="th">🏦 Paiement</th>
          <td>
            #{{ p.id || "?" }} · {{ p.amount != null ? formatEuros(p.amount) : "" }}
            <template v-if="p.state">· {{ stateLabel(p.state) }}</template>
            <template v-if="p.means">· {{ p.means }}</template>
          </td>
        </tr>
        <tr v-for="(f, i) in info.fields" :key="`f${i}`">
          <th :class="th">{{ f.name || "Champ" }}</th>
          <td>
            <b>{{ f.answer || "— vide —" }}</b>
          </td>
        </tr>
        <template v-if="!info.fields.length">
          <tr>
            <th :class="th">🪪 Licence saisie</th>
            <td>
              <b>{{ item.licence_saisie || "— vide —" }}</b>
            </td>
          </tr>
          <tr>
            <th :class="th">🏆 Compétition saisie</th>
            <td>
              <b>{{ item.competition_saisie || "— vide —" }}</b>
            </td>
          </tr>
        </template>
        <template v-for="(o, i) in info.options" :key="`o${i}`">
          <tr>
            <th :class="th">➕ Option</th>
            <td>
              {{ o.name }}
              <template v-if="o.amount">· {{ formatEuros(o.amount) }}</template>
            </td>
          </tr>
          <tr v-for="(f, j) in o.fields" :key="`o${i}f${j}`">
            <th :class="th">{{ f.name || "Champ" }}</th>
            <td>
              <b>{{ f.answer || "— vide —" }}</b>
            </td>
          </tr>
        </template>
        <tr>
          <th :class="th">🔢 N° article</th>
          <td>{{ item.id_item }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!info.itemName && !info.orderId && !info.payerName" class="text-xs text-amber-700">
      ⚠️ HelloAsso n'a transmis que le montant de cet article : synchronisez, ou cherchez le n° d'article sur HelloAsso.
    </p>
    <details v-if="Object.keys(info.raw).length" class="text-xs">
      <summary class="cursor-pointer text-slate-500">🔎 Données brutes HelloAsso</summary>
      <pre class="mt-1 max-h-48 overflow-auto rounded-lg bg-slate-50 p-2">{{ JSON.stringify(info.raw, null, 2) }}</pre>
    </details>

    <template v-if="!ignored">
      <div>
        <label for="attach-comp" :class="label">Compétition</label>
        <select id="attach-comp" v-model="competitionId" data-testid="attach-comp" :class="field">
          <option :value="null">— Aucune (ne pas rattacher) —</option>
          <option v-for="c in current" :key="c.id" :value="c.id">{{ c.nom }} ({{ c.date_competition || "?" }})</option>
          <optgroup v-if="archived.length" label="📦 Archivées">
            <option v-for="c in archived" :key="c.id" :value="c.id">{{ c.nom }} ({{ c.date_competition || "?" }})</option>
          </optgroup>
        </select>
      </div>
      <div>
        <label for="attach-member" :class="label">Athlète</label>
        <select id="attach-member" v-model="adherentId" data-testid="attach-member" :class="field">
          <option :value="null">— Aucun athlète —</option>
          <option v-for="m in members" :key="m.id ?? `${m.nom}${m.prenom}`" :value="m.id">
            {{ m.nom }} {{ m.prenom }} ({{ m.licence_ffme || "sans licence" }})
          </option>
        </select>
      </div>
    </template>
    <div>
      <label for="attach-comment" :class="label">
        {{ ignored ? "Motif / commentaire" : linked ? "Commentaire (optionnel)" : "Commentaire (obligatoire pour ignorer la ligne)" }}
      </label>
      <textarea id="attach-comment" v-model="comment" rows="2" data-testid="attach-comment" :class="field" />
      <p v-if="missingReason" class="mt-1 text-xs font-semibold text-red-600" data-testid="attach-error">
        ✍️ Indiquez un commentaire (motif) pour ignorer cette ligne.
      </p>
    </div>
    <UiDialogActions>
      <UiButton variant="muted" @click="emit('cancel')">Fermer</UiButton>
      <UiButton v-if="skippable" variant="muted" data-testid="attach-skip" :disabled="busy" @click="emit('skip')">⏭ Passer</UiButton>
      <UiButton v-if="!linked" variant="muted" data-testid="attach-ignore" :disabled="busy" @click="ignore">
        {{ ignored ? "↩️ Ne plus ignorer" : "🚫 Ignorer" }}
      </UiButton>
      <UiButton v-if="!ignored" type="submit" data-testid="attach-save" :busy="busy && 'Enregistrement…'">
        💾 Enregistrer le rattachement
      </UiButton>
    </UiDialogActions>
  </form>
</template>
