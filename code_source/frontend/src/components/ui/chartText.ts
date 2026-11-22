/* Texts of UiChart: axis labels cut to fit, and the full reading of the hovered bar or slice. */

/** The beginning of the label, cut with « … » past `maxLength` characters (Chart.js would hide the beginning instead). */
export function shortLabel(label: string, maxLength: number): string {
  return label.length > maxLength ? `${label.slice(0, maxLength - 1).trimEnd()}…` : label;
}

/** A value with its unit (« 33 % »), 0 when missing. */
export const figure = (value: number | undefined, unit: string): string => `${value ?? 0}${unit ? ` ${unit}` : ""}`;

/** The whole label of the value at `index` and its figure; with several series, the figure of each series. */
export function hoverText(label: string, datasets: readonly { label: string; data: number[] }[], index: number, unit: string): string {
  if (datasets.length === 1) {
    return `${label} : ${figure(datasets[0]?.data[index], unit)}`;
  }
  return [label, ...datasets.map((dataset) => `${dataset.label} ${figure(dataset.data[index], unit)}`)].join(" · ");
}
