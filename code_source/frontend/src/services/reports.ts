/* API of the reports theme (server: api/reports/): the members map and the pivot table of the Outils page.
   Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createReportsApi(client: ApiClient) {
  return {
    /** Members of the season grouped by address ("active": the active season, "Toutes les saisons": every season). */
    mapPoints: (season: string) => unwrap(client.GET("/api/reports/map-points", { params: { query: { season } } })),
    /** Members of the season as rows of the pivot table (same seasons as mapPoints). */
    pivotRecords: (season: string) => unwrap(client.GET("/api/reports/pivot-records", { params: { query: { season } } })),
  };
}
