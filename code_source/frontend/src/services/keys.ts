/* API of the keys theme (server: api/keys/): the club keys of the climbing wall, Outils › Clés.
   Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createKeysApi(client: ApiClient) {
  return {
    list: () => unwrap(client.GET("/api/keys")),
    add: (code: string) => unwrap(client.POST("/api/keys", { body: { code } })),
  };
}
