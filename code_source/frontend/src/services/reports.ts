/* API of the reports theme (server: api/reports/): the members map and the statistics of the Outils page.
   Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createReportsApi(client: ApiClient) {
  return {
    /** Members of the season grouped by address ("active": the active season, "Toutes les saisons": every season). */
    mapPoints: (season: string) => unwrap(client.GET("/api/reports/map-points", { params: { query: { season } } })),
    /** Every purchase of every season, without names, for the member charts (Outils › Statistiques). */
    memberStats: () => unwrap(client.GET("/api/reports/member-stats")),
  };
}
