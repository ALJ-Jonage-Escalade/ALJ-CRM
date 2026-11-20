/* FFME passport colours (blanc → noir) and their circles, shared by the member pages and the FFME import. */

export const PASSPORT_COLOURS = {
  blanc: "⚪",
  jaune: "🟡",
  orange: "🟠",
  vert: "🟢",
  bleu: "🔵",
  violet: "🟣",
  rouge: "🔴",
  noir: "⚫",
} as const satisfies Record<string, string>;

type PassportColour = keyof typeof PASSPORT_COLOURS;
const PASSPORT_COLOUR = new RegExp(`\\b(${Object.keys(PASSPORT_COLOURS).join("|")})\\b`, "gi");

function isPassportColour(word: string): word is PassportColour {
  return word in PASSPORT_COLOURS;
}

/** The FFME passports as coloured circles (« Passeport Blanc, Passeport Jaune » → ⚪🟡); the text when it names no colour. */
export function passportMarks(passports: string): string {
  const marks = [...passports.matchAll(PASSPORT_COLOUR)]
    .map((match) => (match[1] ?? "").toLowerCase())
    .filter(isPassportColour)
    .map((colour) => PASSPORT_COLOURS[colour]);
  return marks.length > 0 ? marks.join("") : passports;
}
