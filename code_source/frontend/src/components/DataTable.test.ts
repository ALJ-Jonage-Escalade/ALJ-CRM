import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import DataTable from "./DataTable.vue";
import { compareValues, rangeLabel, type DataColumn } from "./dataTable";

interface Row {
  id: number;
  name: string;
  date: string;
  age: number | null;
}

const COLUMNS: DataColumn<Row>[] = [
  { id: "name", label: "Nom", value: (r) => r.name },
  { id: "date", label: "Date", value: (r) => r.date, descFirst: true },
  { id: "age", label: "Âge", value: (r) => r.age },
  { id: "link", label: "Lien", value: () => "", fixed: true },
];

const rowsOf = (names: string[]): Row[] =>
  names.map((name, i) => ({ id: i + 1, name, date: `2026-09-${String(10 + i)}`, age: i % 3 ? i : null }));

function render(rows: Row[], pageSize = 50, extra: { hidden?: string[]; selectedKey?: string; onRowClick?: (row: Row) => void } = {}) {
  const data = ref(rows);
  const reset = ref("");
  const hidden = ref(extra.hidden ?? []);
  const wrapper = mount(
    defineComponent({
      setup: () => () =>
        h(
          DataTable<Row>,
          {
            rows: data.value,
            columns: COLUMNS,
            rowKey: (r: Row) => String(r.id),
            sort: { id: "name" },
            pageSize,
            resetKey: reset.value,
            label: "Test",
            empty: "Rien.",
            ...extra,
            hidden: hidden.value,
          },
          {
            "cell-link": ({ row }: { row: Row }) => h("a", { href: `/r/${row.id}` }, "voir"),
            card: ({ row }: { row: Row }) => h("b", row.name),
          },
        ),
    }),
  );
  const names = () => wrapper.findAll('[data-testid="data-row"]').map((tr) => tr.find("td").text());
  return { wrapper, data, reset, hidden, names };
}

describe("DataTable", () => {
  it("sorts by the initial column, then by the clicked one (dates from the latest first)", async () => {
    const { wrapper, names } = render(rowsOf(["émile", "Zoé", "adam", "Élodie"]));
    expect(names()).toEqual(["adam", "Élodie", "émile", "Zoé"]); // accents and case ignored
    expect(wrapper.find("th[aria-sort]").attributes("aria-sort")).toBe("ascending");

    await wrapper.find('[data-testid="sort-name"]').trigger("click");
    expect(names()).toEqual(["Zoé", "émile", "Élodie", "adam"]);

    await wrapper.find('[data-testid="sort-date"]').trigger("click");
    expect(names()).toEqual(["Élodie", "adam", "Zoé", "émile"]);
    expect(wrapper.find('[data-testid="sort-link"]').exists()).toBe(false);
  });

  it("renders the page's cell and card slots, and the empty message", async () => {
    const { wrapper, data } = render(rowsOf(["Ana"]));
    expect(wrapper.find('[data-testid="data-row"] a').attributes("href")).toBe("/r/1");
    expect(wrapper.find('[data-testid="data-card"]').text()).toBe("Ana");
    expect(wrapper.find('[data-testid="data-row"]').attributes("data-id")).toBe("1");
    data.value = [];
    await nextTick();
    expect(wrapper.find('[data-testid="data-empty"]').text()).toBe("Rien.");
  });

  it("pages the rows, keeps the page when the rows change and goes back to the first on resetKey", async () => {
    const names = Array.from({ length: 7 }, (_, i) => `n${i}`);
    const { wrapper, data, reset, names: shown } = render(rowsOf(names), 3);
    expect(shown()).toEqual(["n0", "n1", "n2"]);
    expect(wrapper.find('[data-testid="pager-range"]').text()).toBe("1–3 sur 7");
    await wrapper.find('[data-testid="pager-next"]').trigger("click");
    await wrapper.find('[data-testid="pager-next"]').trigger("click");
    expect(shown()).toEqual(["n6"]);
    expect(wrapper.find('[data-testid="pager-next"]').attributes("disabled")).toBeDefined();

    data.value = rowsOf([...names, "n7"]); // polled again: same page
    await nextTick();
    expect(shown()).toEqual(["n6", "n7"]);

    data.value = rowsOf(names.slice(0, 4)); // the page no longer exists: last page
    await nextTick();
    await nextTick();
    expect(shown()).toEqual(["n3"]);

    reset.value = "other filters";
    await nextTick();
    expect(shown()).toEqual(["n0", "n1", "n2"]);
  });

  it("hides the given columns, keeping their sort", async () => {
    const { wrapper, hidden } = render(rowsOf(["Ana", "Bob"]), 50, { hidden: ["date", "link"] });
    const headers = () => wrapper.findAll("th").map((th) => th.text());
    expect(headers()).toEqual(["Nom ▲", "Âge"]);
    expect(wrapper.find('[data-testid="data-row"]').findAll("td")).toHaveLength(2);
    hidden.value = [];
    await nextTick();
    expect(headers()).toEqual(["Nom ▲", "Date", "Âge", "Lien"]);
  });

  it("marks the selected row and card, and reports clicks on a row or card but not on a link inside", async () => {
    const clicked: string[] = [];
    const { wrapper } = render(rowsOf(["Ana", "Bob"]), 50, { selectedKey: "2", onRowClick: (r) => clicked.push(r.name) });
    const rows = wrapper.findAll('[data-testid="data-row"]');
    expect(rows.map((r) => r.attributes("aria-selected"))).toEqual(["false", "true"]);
    expect(wrapper.findAll('[data-testid="data-card"]').map((c) => c.attributes("aria-current"))).toEqual([undefined, "true"]);
    await rows[0]!.find("td").trigger("click");
    rows[0]!.find("a").element.addEventListener("click", (e) => e.preventDefault()); // jsdom does not navigate
    await rows[0]!.find("a").trigger("click");
    await wrapper.findAll('[data-testid="data-card"]')[1]!.trigger("click");
    expect(clicked).toEqual(["Ana", "Bob"]);
  });

  it("has no selection nor clickable rows unless asked", () => {
    const { wrapper } = render(rowsOf(["Ana"]));
    const row = wrapper.find('[data-testid="data-row"]');
    expect(row.attributes("aria-selected")).toBeUndefined();
    expect(row.classes()).not.toContain("cursor-pointer");
  });

  it("hides the pager when everything fits", () => {
    const { wrapper } = render(rowsOf(["a", "b"]), 3);
    expect(wrapper.find('[data-testid="pager"]').exists()).toBe(false);
  });
});

describe("compareValues / rangeLabel", () => {
  it("compares numbers by value with empty first, and text in French order", () => {
    expect([5, null, 12, 3].sort(compareValues)).toEqual([null, 3, 5, 12]);
    expect(["U11", "U9", "été", "Eva"].sort(compareValues)).toEqual(["été", "Eva", "U9", "U11"]);
    expect(rangeLabel(1, 50, 120)).toBe("51–100 sur 120");
    expect(rangeLabel(0, 50, 0)).toBe("0 sur 0");
  });
});
