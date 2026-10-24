/* Columns and TanStack Table setup of the app's data table (DataTable.vue, plan decision D5): sorting and pagination
   on the client. The pages describe their columns with DataColumn and never touch TanStack directly; filtering stays
   in the pages' own modules (rows passed in are already filtered). */
import {
  createPaginatedRowModel,
  createSortedRowModel,
  rowPaginationFeature,
  rowSortingFeature,
  tableFeatures,
  type ColumnDef,
  type RowData,
  type SortFn,
} from "@tanstack/vue-table";

export const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
});

export type Features = typeof features;

/** Shown in a cell and compared by the default sort. */
export type CellValue = string | number | null | undefined;

export interface DataColumn<T> {
  id: string;
  label: string;
  /** Tooltip of the header. */
  title?: string;
  value: (row: T) => CellValue;
  /** Ascending order of two rows; default: numbers, then text in French order (case and accents ignored). */
  compare?: (a: T, b: T) => number;
  /** The first click sorts from the highest (dates, scores). */
  descFirst?: boolean;
  /** Not sortable. */
  fixed?: boolean;
  /** Classes of the column's cells (alignment, width). */
  class?: string;
}

const collator = new Intl.Collator("fr", { sensitivity: "base", numeric: true });

/** Numbers by value (empty first), anything else as text. */
export function compareValues(a: CellValue, b: CellValue): number {
  if (typeof a === "number" || typeof b === "number") {
    return (typeof a === "number" ? a : -Infinity) - (typeof b === "number" ? b : -Infinity) || 0;
  }
  return collator.compare(String(a ?? ""), String(b ?? ""));
}

export function columnDefs<T extends RowData>(columns: readonly DataColumn<T>[]): ColumnDef<Features, T>[] {
  return columns.map((c) => {
    const sortFn: SortFn<Features, T> = c.compare
      ? (ra, rb) => c.compare!(ra.original, rb.original)
      : (ra, rb) => compareValues(c.value(ra.original), c.value(rb.original));
    return {
      id: c.id,
      header: c.label,
      accessorFn: (row: T) => c.value(row),
      sortFn,
      sortDescFirst: c.descFirst ?? false,
      enableSorting: !c.fixed,
      sortUndefined: false,
    };
  });
}

/** "1–50 sur 123" */
export function rangeLabel(pageIndex: number, pageSize: number, total: number): string {
  if (!total) {
    return "0 sur 0";
  }
  const first = pageIndex * pageSize + 1;
  return `${first}–${Math.min(total, first + pageSize - 1)} sur ${total}`;
}
