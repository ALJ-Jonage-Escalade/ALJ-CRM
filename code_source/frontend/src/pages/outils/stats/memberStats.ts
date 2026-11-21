/* Member statistics of Outils › Statistiques (plans/stats-charts.md), counted from the rows of
   /api/reports/member-stats: one person per season, validated purchases only. */
import { HEX } from "../../../components/ui/palette";
import type { Schemas } from "../../../lib/client";

export type MemberStatsRecord = Schemas["MemberStatsRecord"];

/** A validated member of a season, once, with every group they paid for. */
export interface SeasonMember {
  userId: number;
  season: string;
  sex: MemberStatsRecord["sex"];
  age: number | null;
  ageBand: string;
  city: string;
  /** Already a member before the season */
  returning: boolean;
  /** YYYY-MM of the first purchase of the season, « Inconnue » */
  orderMonth: string;
  groups: string[];
}

/** A slice of a pie, a bar of a chart. */
export interface Slice {
  label: string;
  count: number;
}

/** The stacked bars of a breakdown: one bar per label, a segment per series. */
export interface Breakdown {
  labels: string[];
  series: { label: string; values: number[] }[];
}

export type Dimension = "sex" | "group" | "ageBand" | "city" | "returning" | "orderMonth" | "season";

const OTHERS = "Autres";

const SEX_LABELS = { F: "Femmes", H: "Hommes" } as const;
const SEX_UNKNOWN = "Non renseigné";
const SEX_ORDER = [SEX_LABELS.F, SEX_LABELS.H, SEX_UNKNOWN];
const NEW = "Nouveaux";
const RETURNING = "Renouvellements";

/** Colour of each category, the same on every chart; unknown values in grey. */
export const CATEGORY_COLORS: Record<string, string> = {
  [SEX_LABELS.F]: HEX.violet,
  [SEX_LABELS.H]: HEX.teal,
  [SEX_UNKNOWN]: HEX.slate,
  [NEW]: HEX.amber,
  [RETURNING]: HEX.blue,
};

/** How a dimension reads a member (several values: a member in several groups) and orders its values. */
interface DimensionRule {
  values: (member: SeasonMember) => string[];
  order: (counts: ReadonlyMap<string, number>) => string[];
  /** Only the `top` values with the most members are kept, the others merged in « Autres » (shown last). */
  top?: number;
}

const byFixedOrder = (order: readonly string[]) => (counts: ReadonlyMap<string, number>) => order.filter((label) => counts.has(label));
const largestFirst = (counts: ReadonlyMap<string, number>) =>
  [...counts.keys()].sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0) || a.localeCompare(b));

/** The server's age bands start with their lower bound (« 10 à 17 ans »); « Inconnue » has none and goes last. */
function lowerBound(band: string): number {
  const bound = Number.parseInt(band, 10);
  return Number.isNaN(bound) ? Number.MAX_SAFE_INTEGER : bound;
}
/** YYYY-MM sorts as text, before « Inconnue ». */
const byText = (counts: ReadonlyMap<string, number>) => [...counts.keys()].sort();
const byAge = (counts: ReadonlyMap<string, number>) => [...counts.keys()].sort((a, b) => lowerBound(a) - lowerBound(b));

const DIMENSIONS: Record<Dimension, DimensionRule> = {
  sex: { values: (member) => [member.sex ? SEX_LABELS[member.sex] : SEX_UNKNOWN], order: byFixedOrder(SEX_ORDER) },
  group: { values: (member) => member.groups, order: largestFirst },
  ageBand: { values: (member) => [member.ageBand], order: byAge },
  city: { values: (member) => [member.city], order: largestFirst, top: 10 },
  returning: { values: (member) => [member.returning ? RETURNING : NEW], order: byFixedOrder([NEW, RETURNING]) },
  orderMonth: { values: (member) => [member.orderMonth], order: byText },
  season: { values: (member) => [member.season], order: byText },
};

/** The validated members of the season, one per person, their groups merged. */
export function seasonMembers(records: readonly MemberStatsRecord[], season: string): SeasonMember[] {
  const members = new Map<number, SeasonMember>();
  for (const record of records) {
    if (record.season !== season || record.status !== "Validé") {
      continue;
    }
    const member = members.get(record.user_id);
    if (member) {
      member.groups.push(record.group);
      member.returning ||= record.returning;
      member.orderMonth = [member.orderMonth, record.order_month].sort()[0] ?? record.order_month;
    } else {
      members.set(record.user_id, {
        userId: record.user_id,
        season,
        sex: record.sex,
        age: record.age ?? null,
        ageBand: record.age_band,
        city: record.city,
        returning: record.returning,
        orderMonth: record.order_month,
        groups: [record.group],
      });
    }
  }
  return [...members.values()];
}

function countValues(members: readonly SeasonMember[], values: (member: SeasonMember) => string[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const member of members) {
    for (const label of values(member)) {
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
  }
  return counts;
}

/** The labels of a member for the dimension among these members: the values outside the top merged in « Autres ». */
function labeller(members: readonly SeasonMember[], dimension: Dimension): (member: SeasonMember) => string[] {
  const { values, top } = DIMENSIONS[dimension];
  if (top === undefined) {
    return values;
  }
  const kept = new Set(largestFirst(countValues(members, values)).slice(0, top));
  return (member) => [...new Set(values(member).map((label) => (kept.has(label) ? label : OTHERS)))];
}

function counted(members: readonly SeasonMember[], dimension: Dimension): Map<string, number> {
  return countValues(members, labeller(members, dimension));
}

/** Members per value of the dimension, in the dimension's order. */
export function countBy(members: readonly SeasonMember[], dimension: Dimension): Slice[] {
  const counts = counted(members, dimension);
  const others = counts.get(OTHERS);
  counts.delete(OTHERS);
  const slices = DIMENSIONS[dimension].order(counts).map((label) => ({ label, count: counts.get(label) ?? 0 }));
  return others === undefined ? slices : [...slices, { label: OTHERS, count: others }];
}

/** `dimension` per value of `by`: a series per value of the dimension, a bar per value of `by`; in percent, each bar
    is split in rounded percentages of its own members. */
export function breakdown(members: readonly SeasonMember[], dimension: Dimension, by: Dimension, mode: "count" | "percent"): Breakdown {
  const bars = countBy(members, by);
  const seriesLabels = countBy(members, dimension).map((slice) => slice.label);
  const barLabels = labeller(members, by);
  const seriesLabelsOf = labeller(members, dimension);
  const series = seriesLabels.map((label) => ({
    label,
    values: bars.map((bar) => {
      const count = members.filter((member) => barLabels(member).includes(bar.label) && seriesLabelsOf(member).includes(label)).length;
      return mode === "count" ? count : Math.round((count / bar.count) * 100);
    }),
  }));
  return { labels: bars.map((bar) => bar.label), series };
}

/** The figures of the season's cards; percentages and average age null without members (or known ages). */
export interface MemberCards {
  members: number;
  newPercent: number | null;
  /** Average of the known ages, one decimal */
  averageAge: number | null;
  /** Purchases cancelled in the season (a member who registered again is still counted) */
  cancelled: number;
}

const percentOf = (part: number, total: number): number | null => (total ? Math.round((part / total) * 100) : null);

/** members: seasonMembers(records, season), already computed by the page. */
export function memberCards(members: readonly SeasonMember[], records: readonly MemberStatsRecord[], season: string): MemberCards {
  const ages = members.flatMap((member) => (member.age === null ? [] : [member.age]));
  return {
    members: members.length,
    newPercent: percentOf(members.filter((member) => !member.returning).length, members.length),
    averageAge: ages.length ? Math.round((ages.reduce((sum, age) => sum + age, 0) / ages.length) * 10) / 10 : null,
    cancelled: records.filter((record) => record.season === season && record.status === "Annulé").length,
  };
}

/** The members of every season by sex, oldest season first. */
export function membersPerSeason(records: readonly MemberStatsRecord[]): Breakdown {
  const seasons = new Set(records.map((record) => record.season));
  const members = [...seasons].flatMap((season) => seasonMembers(records, season));
  return breakdown(members, "sex", "season", "count");
}
