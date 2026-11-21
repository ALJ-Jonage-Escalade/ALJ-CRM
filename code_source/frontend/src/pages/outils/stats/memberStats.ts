/* Member statistics of Outils › Statistiques (plans/stats-charts.md), counted from the rows of
   /api/reports/member-stats: one person per season, validated purchases only. */
import { HEX } from "../../../components/ui/palette";
import type { Schemas } from "../../../lib/client";

export type MemberStatsRecord = Schemas["MemberStatsRecord"];

/** A validated member of a season, once, with every group they paid for. */
export interface SeasonMember {
  userId: number;
  sex: MemberStatsRecord["sex"];
  groups: string[];
}

/** A slice of a pie, a bar of a chart. */
export interface Slice {
  label: string;
  count: number;
}

export type Dimension = "sex";

const SEX_LABELS = { F: "Femmes", H: "Hommes" } as const;
export const SEX_UNKNOWN = "Non renseigné";
const SEX_ORDER = [SEX_LABELS.F, SEX_LABELS.H, SEX_UNKNOWN];

/** Colour of each category, the same on every chart; unknown values in grey. */
export const CATEGORY_COLORS: Record<string, string> = {
  [SEX_LABELS.F]: HEX.violet,
  [SEX_LABELS.H]: HEX.teal,
  [SEX_UNKNOWN]: HEX.slate,
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
    } else {
      members.set(record.user_id, { userId: record.user_id, sex: record.sex, groups: [record.group] });
    }
  }
  return [...members.values()];
}

function sexLabel(sex: MemberStatsRecord["sex"]): string {
  return sex ? SEX_LABELS[sex] : SEX_UNKNOWN;
}

/** Members per value of the dimension, in the dimension's order, empty values left out. */
export function countBy(members: readonly SeasonMember[], dimension: Dimension): Slice[] {
  const counts = new Map<string, number>();
  for (const member of members) {
    const label = dimension === "sex" ? sexLabel(member.sex) : "";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return SEX_ORDER.filter((label) => counts.has(label)).map((label) => ({ label, count: counts.get(label) ?? 0 }));
}
