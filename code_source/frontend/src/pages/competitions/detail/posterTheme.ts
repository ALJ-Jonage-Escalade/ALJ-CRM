/* The colours of the results poster, in one place to tune them after the club's feedback. The poster reads them as
   CSS variables (--poster-primary…); its podium colours are its own, changing them leaves the app's badges as they are. */

export const POSTER_THEME = {
  background: "#ffffff",
  text: "#0f172a",
  muted: "#64748b",
  primary: "#1e3a8a", // header, climber names: the club's dark blue
  accent: "#ea580c", // rule under the header, category titles: the club's orange
  zebra: "#f1f5f9", // every other row
  gold: "#eab308",
  silver: "#71717a",
  bronze: "#c2410c",
} as const;

/** The theme as the CSS variables of the poster's root element. */
export const posterThemeStyle = (): Record<string, string> =>
  Object.fromEntries(Object.entries(POSTER_THEME).map(([name, colour]) => [`--poster-${name}`, colour]));
