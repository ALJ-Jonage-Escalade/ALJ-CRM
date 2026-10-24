<script setup lang="ts" generic="T extends RowData">
/* Responsive data table of the app: a sortable table on desktop, stacked cards on phones (below md), pages of
   pageSize rows. Columns: DataColumn (dataTable.ts). A cell shows its value, or the page's slot `cell-<column id>`;
   a card shows the `card` slot. sortedRows() (exposed) gives every row in the order shown (exports). Sorting and
   paging are kept when the rows change (polling); resetKey sends back to the first page (new filters). hidden: ids of
   columns not shown (their sort still applies). onRowClick: a click on a row or card, except on a link or a control
   inside it; selectedKey: the row key shown as selected. */
import { useTable, type RowData, type SortingState } from "@tanstack/vue-table";
import { computed, toRef, watch } from "vue";
import { columnDefs, features, rangeLabel, type CellValue, type DataColumn } from "./dataTable";

const props = withDefaults(
  defineProps<{
    rows: readonly T[];
    columns: readonly DataColumn<T>[];
    rowKey: (row: T) => string;
    sort: { id: string; desc?: boolean };
    pageSize?: number;
    empty?: string;
    resetKey?: unknown;
    /** Accessible name of the table. */
    label: string;
    hidden?: readonly string[];
    selectedKey?: string;
    /** A prop rather than an emit, so the rows are only clickable when the page listens. */
    onRowClick?: (row: T) => void;
  }>(),
  { pageSize: 50, empty: "Aucune ligne.", resetKey: undefined, hidden: () => [], selectedKey: undefined, onRowClick: undefined },
);

defineSlots<{
  [cell: `cell-${string}`]: (props: { row: T; value: CellValue }) => unknown;
  card(props: { row: T }): unknown;
}>();

// The columns of a table do not change: read once
const byId = new Map(props.columns.map((c) => [c.id, c]));

const table = useTable({
  features,
  columns: columnDefs(props.columns),
  data: toRef(props, "rows"),
  getRowId: (row: T) => props.rowKey(row),
  initialState: {
    sorting: [{ id: props.sort.id, desc: props.sort.desc ?? false }] as SortingState,
    pagination: { pageIndex: 0, pageSize: props.pageSize },
  },
  enableSortingRemoval: false,
  enableMultiSort: false,
  autoResetPageIndex: false,
});

watch(
  () => props.resetKey,
  () => table.setPageIndex(0),
  { deep: true },
);
// Fewer rows than before (a member left the season): stay on a page that exists
watch(
  () => table.getPageCount(),
  (count) => {
    if (table.atoms.pagination.get().pageIndex >= count) {
      table.setPageIndex(Math.max(0, count - 1));
    }
  },
);

const pageRows = computed(() => table.getRowModel().rows);
const hiddenIds = computed(() => new Set(props.hidden));
const visibleCount = computed(() => props.columns.filter((c) => !hiddenIds.value.has(c.id)).length);

function rowClicked(event: MouseEvent, row: T): void {
  // A link (the record, mailto, tel) or a control does its own job
  if ((event.target as Element | null)?.closest("a, button, input, select, textarea, label")) {
    return;
  }
  props.onRowClick?.(row);
}
const isSelected = (id: string) => props.selectedKey !== undefined && id === props.selectedKey;

defineExpose({
  /** Every row (all pages) in the order shown, e.g. for an export. */
  sortedRows: (): T[] => table.getSortedRowModel().rows.map((r) => r.original),
});
const pageIndex = computed(() => table.atoms.pagination.get().pageIndex);
const total = computed(() => props.rows.length);
const ariaSort = (dir: false | "asc" | "desc") => (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : undefined);
const sortIcon = (dir: false | "asc" | "desc") => (dir === "asc" ? "▲" : dir === "desc" ? "▼" : "");
</script>

<template>
  <div>
    <!-- Desktop: table -->
    <div class="hidden overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm md:block">
      <table class="w-full border-collapse text-[12.5px]" :aria-label="label" data-testid="data-table">
        <thead class="bg-slate-50 text-left text-[11.5px] tracking-wide text-slate-500 uppercase">
          <tr v-for="group in table.getHeaderGroups()" :key="group.id">
            <th
              v-for="header in group.headers.filter((h) => !hiddenIds.has(h.column.id))"
              :key="header.id"
              scope="col"
              :aria-sort="ariaSort(header.column.getIsSorted())"
              :title="byId.get(header.column.id)?.title"
              :class="['border-b border-slate-200 px-2.5 py-2 font-bold whitespace-nowrap', byId.get(header.column.id)?.class]"
            >
              <button
                v-if="header.column.getCanSort()"
                type="button"
                :data-testid="`sort-${header.column.id}`"
                class="inline-flex cursor-pointer items-center gap-1 uppercase hover:text-slate-800"
                :class="header.column.getIsSorted() && 'text-accent'"
                @click="header.column.toggleSorting()"
              >
                {{ byId.get(header.column.id)?.label }}
                <span aria-hidden="true" class="w-2.5 text-[10px]">{{ sortIcon(header.column.getIsSorted()) }}</span>
              </button>
              <template v-else>{{ byId.get(header.column.id)?.label }}</template>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!pageRows.length">
            <td :colspan="visibleCount" class="px-2.5 py-8 text-center text-slate-500" data-testid="data-empty">{{ empty }}</td>
          </tr>
          <tr
            v-for="row in pageRows"
            :key="row.id"
            data-testid="data-row"
            :data-id="row.id"
            :aria-selected="selectedKey !== undefined ? isSelected(row.id) : undefined"
            :class="[
              'border-b border-slate-100 last:border-0',
              isSelected(row.id) ? 'bg-accent/10' : 'hover:bg-slate-50',
              onRowClick && 'cursor-pointer',
            ]"
            @click="rowClicked($event, row.original)"
          >
            <td
              v-for="(cell, i) in row.getAllCells().filter((c) => !hiddenIds.has(c.column.id))"
              :key="cell.id"
              :class="[
                'px-2.5 py-1.5 align-middle',
                byId.get(cell.column.id)?.class,
                i === 0 && isSelected(row.id) && 'shadow-[inset_3px_0_0_var(--color-accent)]',
              ]"
            >
              <slot :name="`cell-${cell.column.id}`" :row="row.original" :value="cell.getValue() as CellValue">{{
                cell.getValue() ?? ""
              }}</slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Phones: one card per row, in the same order -->
    <ul class="flex flex-col gap-2 md:hidden" :aria-label="label" data-testid="data-cards">
      <li v-if="!pageRows.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">{{ empty }}</li>
      <li
        v-for="row in pageRows"
        :key="row.id"
        data-testid="data-card"
        :data-id="row.id"
        :aria-current="isSelected(row.id) || undefined"
        :class="[
          'rounded-xl border bg-white px-3.5 py-3 shadow-sm',
          isSelected(row.id) ? 'border-accent ring-1 ring-accent' : 'border-slate-200',
          onRowClick && 'cursor-pointer',
        ]"
        @click="rowClicked($event, row.original)"
      >
        <slot name="card" :row="row.original" />
      </li>
    </ul>

    <nav
      v-if="table.getPageCount() > 1"
      class="mt-2.5 flex flex-wrap items-center justify-end gap-2 text-xs text-slate-600"
      aria-label="Pages"
      data-testid="pager"
    >
      <span data-testid="pager-range">{{ rangeLabel(pageIndex, pageSize, total) }}</span>
      <button
        type="button"
        data-testid="pager-prev"
        class="cursor-pointer rounded-lg bg-slate-200 px-2.5 py-1.5 font-bold hover:bg-slate-300 disabled:cursor-default disabled:opacity-50"
        :disabled="!table.getCanPreviousPage()"
        @click="table.previousPage()"
      >
        ‹ Précédents
      </button>
      <button
        type="button"
        data-testid="pager-next"
        class="cursor-pointer rounded-lg bg-slate-200 px-2.5 py-1.5 font-bold hover:bg-slate-300 disabled:cursor-default disabled:opacity-50"
        :disabled="!table.getCanNextPage()"
        @click="table.nextPage()"
      >
        Suivants ›
      </button>
    </nav>
  </div>
</template>
