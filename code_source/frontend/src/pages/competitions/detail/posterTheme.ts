/* The colours of the results poster, in one place to tune them after the club's feedback. The poster reads them as
   CSS variables (--poster-primary…). The result badges are not here: they are the competition page's (palette.ts SOFT). */

export const POSTER_THEME = {
  background: "#ffffff",
  text: "#0f172a",
  muted: "#64748b",
  primary: "#1e3a8a", // header, climber names: the club's dark blue
  accent: "#ea580c", // rule under the header, category titles: the club's orange
  divider: "#e2e8f0", // line above the footer
} as const;

/** The theme as the CSS variables of the poster's root element. */
export const posterThemeStyle = (): Record<string, string> =>
  Object.fromEntries(Object.entries(POSTER_THEME).map(([name, colour]) => [`--poster-${name}`, colour]));
