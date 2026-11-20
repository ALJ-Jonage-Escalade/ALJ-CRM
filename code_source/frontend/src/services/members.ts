/* API of the members theme (server: api/members/): member records, seasons and the HelloAsso membership import.
   Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient, type ApiRead, type Schemas } from "../lib/client";

/** A membership status (« Validé », « Terminé »…), as the contract types it. */
export type MemberStatus = NonNullable<Schemas["NewMember"]["status"]>;

/** A correctable field of a HelloAsso registration (server: member_data_rules.IssueField). */
export type MembershipField = Schemas["MembershipIssue"]["field"];

/** The members of a season (useSyncedResource), the active one for an empty season. */
export function membersRead(season: string): ApiRead<"/api/members"> {
  return season ? { path: "/api/members", query: { season } } : { path: "/api/members" };
}

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createMembersApi(client: ApiClient) {
  return {
    create: (body: Schemas["MemberCreate"]) => unwrap(client.POST("/api/members/create", { body })),
    update: (body: Schemas["MemberUpdate"]) => unwrap(client.POST("/api/members/update", { body })),
    /** Members of the active season (one row per membership). */
    list: () => unwrap(client.GET("/api/members")),
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
    /** Saves the admin's correction of one field of a registration; answers the preview recomputed with it. */
    helloAssoSaveCorrection: (itemId: number, field: MembershipField, value: string, campaign: string | null) =>
      unwrap(
        client.PUT("/api/helloasso/memberships/corrections/{item_id}/{field}", {
          params: { path: { item_id: itemId, field } },
          body: { value, campaign },
        }),
      ),
    /** Removes the correction of one field (HelloAsso's value applies again); answers the preview recomputed. */
    helloAssoRemoveCorrection: (itemId: number, field: MembershipField, campaign: string | null) =>
      unwrap(
        client.DELETE("/api/helloasso/memberships/corrections/{item_id}/{field}", {
          params: { path: { item_id: itemId, field }, query: campaign ? { campaign } : {} },
        }),
      ),
    /** Checks a value with the import's rules, nothing saved: the value as it would be stored, and its issues. */
    helloAssoCheckValue: (field: MembershipField, value: string) =>
      unwrap(client.POST("/api/helloasso/memberships/corrections/check", { body: { field, value } })),
  };
}
