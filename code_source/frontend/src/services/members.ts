/* API of the members theme (server: api/members/): member records and seasons.
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
  };
}
