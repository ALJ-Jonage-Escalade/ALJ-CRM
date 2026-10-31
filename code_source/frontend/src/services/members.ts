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
    /** The HelloAsso membership campaign set in Paramètres, and the form slug it resolves to. */
    membershipCampaign: () => unwrap(client.GET("/api/settings/helloasso-membership")),
    /** Slug or HelloAsso URL; empty: back to the default campaign of the season. */
    saveMembershipCampaign: (campaign: string) => unwrap(client.POST("/api/settings/helloasso-membership", { body: { campaign } })),
    /** Reads the HelloAsso membership campaign and sorts its registrations for the active season; writes nothing. */
    helloAssoPreview: () => unwrap(client.POST("/api/helloasso/memberships/preview")),
  };
}
