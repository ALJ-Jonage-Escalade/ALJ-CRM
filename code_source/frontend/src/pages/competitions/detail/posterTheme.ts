/* The colours of the results poster, in one place to tune them after the club's feedback. The poster reads them as
   CSS variables (--poster-title…). The result badges are not here: they are the competition page's (palette.ts SOFT). */

export const POSTER_THEME = {
  // Page background: a diagonal gradient, light blue to peach
  "page-from": "#eff6ff",
  "page-via": "#dbeafe",
  "page-to": "#ffedd5",
  // Banner: white to light blue, the volume drawn on its right
  "banner-from": "#ffffff",
  "banner-to": "#dbeafe",
  volume: "#f97316",
  // Texts
  title: "#1e3a8a", // competition name, category titles, strip and footer: the club's dark blue
  accent: "#ea580c", // « RÉSULTATS », « Bravo à tous ! »: the club's orange
  name: "#1e293b", // climbers
  muted: "#475569", // date and place
  // Light bands (figures under the banner, footer) and category cards
  band: "rgb(255 255 255 / 0.7)",
  "band-border": "#fed7aa",
  card: "rgb(255 255 255 / 0.9)",
  "card-line": "#f1f5f9", // between two climbers
  // A hold drawn faintly in the corner of each card
  watermark: "#fb923c",
  "watermark-opacity": "0.25",
} as const;

/** The theme as the CSS variables of the poster's root element. */
export const posterThemeStyle = (): Record<string, string> =>
  Object.fromEntries(Object.entries(POSTER_THEME).map(([name, value]) => [`--poster-${name}`, value]));
