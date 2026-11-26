/* The results poster of a competition (shared as a PNG on WhatsApp): its ranked climbers in category blocks. */
import type { BadgeColor } from "../../../components/ui/palette";
import { rankingColor, rankingText, type Participant } from "../competitions";

/** A climber's line: the place as on the competition page (« 🥇 1 / 25 », « 4 / 19 ») and its badge colour. */
export interface PosterLine {
  name: string;
  place: string;
  color: BadgeColor;
}

export interface PosterBlock {
  title: string;
  lines: PosterLine[];
}

const rankOf = (participant: Participant): number => Number.parseInt(String(participant.classement ?? "").trim(), 10);

/* « U13 Femme », « U13Femme », « [U13] F », « Senior H »… as MyCompet writes them (accents removed first). */
const CATEGORY = /^(u\d{1,2}|senior|veteran)\s*(femme|homme|f|h)?$/;
const AGE_NAMES: Record<string, string> = { senior: "Sénior", veteran: "Vétéran" };
const SEX_NAMES: Record<string, string> = { f: "Femme", femme: "Femme", h: "Homme", homme: "Homme" };

/* Block order: the age (U.. by its number, then adults), then women, mixed, men; unknown categories last. */
const AGE_ORDER: Record<string, number> = { senior: 100, veteran: 101 };
const UNKNOWN_AGE = 1000;
const SEX_ORDER: Record<string, number> = { Femme: 0, "": 1, Homme: 2 };

interface Category {
  title: string;
  order: [age: number, sex: number];
}

/** A MyCompet category written one way (« U13 Femme »); the label as is when it is not a known category. Without a
    sex in the label, none is added: such a category can rank boys and girls together. */
function categoryOf(label: string): Category {
  const plain = label
    .normalize("NFD")
    .replace(/[̀-ͯ[\]]/g, "")
    .trim()
    .toLowerCase();
  const found = CATEGORY.exec(plain);
  if (!found) {
    return { title: label.trim(), order: [UNKNOWN_AGE, 0] };
  }
  const [, age = "", sexCode = ""] = found;
  const sex = SEX_NAMES[sexCode] ?? "";
  return {
    title: [AGE_NAMES[age] ?? age.toUpperCase(), sex].filter(Boolean).join(" "),
    order: [AGE_ORDER[age] ?? Number(age.slice(1)), SEX_ORDER[sex] ?? 1],
  };
}

const byName = (a: string, b: string): number => a.localeCompare(b, "fr");

/** The climbers with a place, in one block per category, best placed first. */
export function posterBlocks(participants: readonly Participant[]): PosterBlock[] {
  const groups = new Map<string, { category: Category; climbers: Participant[] }>();
  for (const participant of participants.filter((p) => Number.isInteger(rankOf(p)))) {
    const category = categoryOf(String(participant.categorie_ffme ?? ""));
    const group = groups.get(category.title) ?? { category, climbers: [] };
    group.climbers.push(participant);
    groups.set(category.title, group);
  }
  const nameOf = (participant: Participant): string => `${participant.nom ?? ""} ${participant.prenom ?? ""}`.trim();
  return [...groups.values()]
    .sort(({ category: a }, { category: b }) => a.order[0] - b.order[0] || a.order[1] - b.order[1] || byName(a.title, b.title))
    .map(({ category, climbers }) => ({
      title: category.title,
      lines: climbers
        .sort((a, b) => rankOf(a) - rankOf(b) || byName(nameOf(a), nameOf(b)))
        .map((participant) => ({ name: nameOf(participant), place: rankingText(participant), color: rankingColor(participant) })),
    }));
}

export interface PosterSummary {
  ranked: number;
  podiums: number;
}

/** The figures under the banner: the climbers with a place, and how many of them are on a podium (1st to 3rd). */
export function posterSummary(blocks: readonly PosterBlock[]): PosterSummary {
  const lines = blocks.flatMap((block) => block.lines);
  return { ranked: lines.length, podiums: lines.filter((line) => line.color !== "slate").length };
}
