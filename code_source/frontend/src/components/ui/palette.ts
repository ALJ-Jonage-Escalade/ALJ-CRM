/* The colour names of the app's labels (badges, calendar bars) and their classes. A colour is a name of this palette,
   never a Tailwind class: Tailwind only generates the classes written out in full in the source. */
export type BadgeColor = "slate" | "green" | "amber" | "orange" | "red" | "pink" | "violet" | "indigo" | "blue" | "sky" | "teal";

/** White text on a filled colour (a state). */
export const SOLID: Record<BadgeColor, string> = {
  slate: "bg-slate-400",
  green: "bg-green-600",
  amber: "bg-amber-600",
  orange: "bg-orange-600",
  red: "bg-red-600",
  pink: "bg-pink-600",
  violet: "bg-violet-600",
  indigo: "bg-indigo-600",
  blue: "bg-blue-600",
  sky: "bg-sky-600",
  teal: "bg-teal-600",
};

/** Coloured text on a light tag with a border (a piece of information). */
export const SOFT: Record<BadgeColor, string> = {
  slate: "border-slate-200 bg-slate-100 text-slate-600",
  green: "border-green-200 bg-green-50 text-green-700",
  amber: "border-amber-200 bg-amber-50 text-amber-800",
  orange: "border-orange-200 bg-orange-50 text-orange-800",
  red: "border-red-200 bg-red-50 text-red-700",
  pink: "border-pink-200 bg-pink-50 text-pink-800",
  violet: "border-violet-200 bg-violet-50 text-violet-700",
  indigo: "border-indigo-200 bg-indigo-50 text-indigo-800",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  sky: "border-sky-200 bg-sky-50 text-sky-700",
  teal: "border-teal-200 bg-teal-50 text-teal-700",
};

/** The colour as CSS (charts: Chart.js draws on a canvas, Tailwind classes do not apply); the 600 shades, slate 400. */
export const HEX: Record<BadgeColor, string> = {
  slate: "#94a3b8",
  green: "#16a34a",
  amber: "#d97706",
  orange: "#ea580c",
  red: "#dc2626",
  pink: "#db2777",
  violet: "#7c3aed",
  indigo: "#4f46e5",
  blue: "#2563eb",
  sky: "#0284c7",
  teal: "#0d9488",
};
