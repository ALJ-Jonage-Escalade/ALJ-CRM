/* Members map of the Outils page, without Leaflet: the groups of the points, the group filter and the texts of the
   summary. The map itself is in membersMapView.ts. */
import type { Schemas } from "../../lib/client";
import { plural } from "../../lib/text";

export type MapPoint = Schemas["MapPoint"];

/** Every group of the points, sorted. */
export function groupsOf(points: readonly MapPoint[]): string[] {
  return [...new Set(points.flatMap((p) => p.members.map((m) => m.group)))].sort((a, b) => a.localeCompare(b, "fr"));
}

/** The points with their members outside the hidden groups; the points left without a member are dropped. */
export function visiblePoints(points: readonly MapPoint[], hidden: ReadonlySet<string>): MapPoint[] {
  if (hidden.size === 0) {
    return [...points];
  }
  return points.flatMap((point) => {
    const members = point.members.filter((m) => !hidden.has(m.group));
    return members.length ? [{ ...point, members }] : [];
  });
}

/** Label of the group filter button. */
export function filterLabel(groupCount: number, shownCount: number): string {
  if (shownCount === groupCount) {
    return "🧗 Tous les groupes";
  }
  return shownCount === 0 ? "⚠️ Aucun groupe sélectionné" : `🧗 ${shownCount} groupe${plural(shownCount)} filtré${plural(shownCount)}`;
}

/** Members and addresses on the map, and the number of groups shown when some are hidden. */
export function mapSummaryText(visible: readonly MapPoint[], groupCount: number, shownCount: number): string {
  const memberCount = visible.reduce((total, p) => total + p.members.length, 0);
  const filter = shownCount === groupCount ? "" : ` (filtre : ${shownCount} groupe${plural(shownCount)})`;
  return `${memberCount} adhérent${plural(memberCount)} réparti${plural(memberCount)} sur ${visible.length} adresse${plural(visible.length)}${filter}`;
}
