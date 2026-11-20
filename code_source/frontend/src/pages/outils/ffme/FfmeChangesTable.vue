<script setup lang="ts">
/* The changes of the FFME import, one row per matched file row: a checkbox to leave the row out, how it was matched,
   and « ancien → nouveau » for each field it changes; warnings for a member matched twice, a licence already stored
   on another member (left to the office: the stored number may be the right one), or no active registration. */
import UiBadge from "../../../components/ui/UiBadge.vue";
import type { BadgeColor } from "../../../components/ui/palette";
import { passportMarks } from "../../../lib/passports";
import { statusColor } from "../../adherents/members";
import { healthDocumentMark, type RowChange } from "./ffme";

defineProps<{ rows: readonly RowChange[]; excludedRows: ReadonlySet<number>; blockedUserIds: ReadonlySet<number> }>();
const emit = defineEmits<{ toggle: [rowNumber: number] }>();

type Field = RowChange["changes"][number]["field"];
const FIELDS: { field: Field; label: string }[] = [
  { field: "licence", label: "Licence" },
  { field: "passeports", label: "Passeports" },
  { field: "diplomes", label: "Diplômes" },
  { field: "document_sante", label: "Document de santé" },
  { field: "statut", label: "Statut" },
];
const SOURCES: Record<RowChange["source"], { label: string; color: BadgeColor }> = {
  licence: { label: "Licence", color: "green" },
  nom: { label: "Nom", color: "blue" },
  manuel: { label: "Manuel", color: "violet" },
};

function changeOf(row: RowChange, field: Field) {
  return row.changes.find((c) => c.field === field);
}

/** The statuses of a status change: old ones (« Validé / En cours » when the purchases differ), then the new one. */
function statusChange(row: RowChange): { old: string[]; new: string } | undefined {
  const change = changeOf(row, "statut");
  return change && { old: change.old ? change.old.split(" / ") : [], new: change.new };
}

function changeText(row: RowChange, field: Field): string {
  const change = changeOf(row, field);
  return change ? `${change.old || "—"} → ${change.new}` : "";
}

/** The cell: health document ✅ / ❌ and the new value, passports as coloured circles; the full change in the tooltip. */
function cellText(row: RowChange, field: Field): string {
  const change = changeOf(row, field);
  if (change && field === "document_sante") {
    return `${healthDocumentMark(change.new)} ${change.new}`;
  }
  if (change && field === "passeports") {
    return `${passportMarks(change.old) || "—"} → ${passportMarks(change.new)}`;
  }
  return changeText(row, field);
}
</script>

<template>
  <div class="max-h-[32rem] overflow-auto rounded-md border border-slate-200">
    <table class="w-full text-xs">
      <thead class="sticky top-0 bg-slate-50 text-left">
        <tr>
          <th class="px-2 py-1.5"><span class="sr-only">Importer</span></th>
          <th class="px-2.5 py-1.5">Adhérent</th>
          <th class="px-2.5 py-1.5">Rapproché par</th>
          <th v-for="column in FIELDS" :key="column.field" class="px-2.5 py-1.5">{{ column.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.row_number"
          data-testid="ffme-change"
          :class="['border-t border-slate-100 align-top', excludedRows.has(row.row_number) && 'opacity-40']"
        >
          <td class="px-2 py-1.5">
            <input
              type="checkbox"
              data-testid="ffme-keep"
              :checked="!excludedRows.has(row.row_number)"
              :aria-label="`Importer la ligne ${row.row_number} (${row.last_name} ${row.first_name})`"
              @change="emit('toggle', row.row_number)"
            />
          </td>
          <td class="px-2.5 py-1.5">
            <div class="font-semibold">{{ row.last_name }} {{ row.first_name }}</div>
            <div class="text-slate-500">{{ row.birth_date || "—" }} · ligne {{ row.row_number }}</div>
            <div v-if="blockedUserIds.has(row.user_id) && !excludedRows.has(row.row_number)" class="font-semibold text-red-700">
              ⚠️ Adhérent rapproché par plusieurs lignes du fichier
            </div>
            <div v-if="row.licence_conflict" data-testid="ffme-licence-conflict" class="font-semibold text-amber-700">
              ⚠️ Licence {{ row.licence }} déjà enregistrée sur {{ row.licence_conflict }} : à corriger sur sa fiche
            </div>
          </td>
          <td class="px-2.5 py-1.5">
            <UiBadge :color="SOURCES[row.source].color" variant="soft">{{ SOURCES[row.source].label }}</UiBadge>
          </td>
          <td v-for="column in FIELDS" :key="column.field" class="max-w-48 px-2.5 py-1.5">
            <span v-if="column.field === 'statut' && row.no_active_registration" class="font-semibold text-amber-700">
              ⚠️ Aucune inscription active sur la saison
            </span>
            <span
              v-else-if="column.field === 'statut' && statusChange(row)"
              class="flex flex-wrap items-center gap-1"
              :title="changeText(row, column.field)"
            >
              <UiBadge v-for="status in statusChange(row)?.old" :key="status" :color="statusColor(status)" data-testid="ffme-status">
                {{ status }}
              </UiBadge>
              <span v-if="!statusChange(row)?.old.length">—</span>
              →
              <UiBadge :color="statusColor(statusChange(row)?.new ?? '')" data-testid="ffme-status">{{ statusChange(row)?.new }}</UiBadge>
            </span>
            <span v-else class="block truncate" :title="changeText(row, column.field)">{{ cellText(row, column.field) }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
