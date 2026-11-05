/* API of the members theme (server: api/members/): member records, seasons and the HelloAsso membership import.
   Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient, type Schemas } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createMembersApi(client: ApiClient) {
  return {
    create: (body: Schemas["MemberCreate"]) => unwrap(client.POST("/api/members/create", { body })),
    update: (body: Schemas["MemberUpdate"]) => unwrap(client.POST("/api/members/update", { body })),
    seasons: () => unwrap(client.GET("/api/seasons")),
    /** Tariff names of the current season. */
    seasonTarifs: () => unwrap(client.GET("/api/season-tarifs")),
    /** Reads the HelloAsso membership campaign and sorts its registrations for the active season; writes nothing.
        campaign: slug of the form picked for this sync only (never saved), null for the active one. */
    helloAssoPreview: (campaign: string | null) => unwrap(client.POST("/api/helloasso/memberships/preview", { body: { campaign } })),
    /** When the HelloAsso membership import last ran, and who ran it (null before the first one). */
    helloAssoLastSync: () => unwrap(client.GET("/api/helloasso/memberships/last-sync")),
    /** Reads HelloAsso again and applies the decisions (by HelloAsso item id) to the recomputed plan. */
    helloAssoImport: (body: Schemas["MembershipImportRequest"]) => unwrap(client.POST("/api/helloasso/memberships/import", { body })),
  };
}
