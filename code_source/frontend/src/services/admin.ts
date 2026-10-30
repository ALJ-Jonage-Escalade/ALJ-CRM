/* API of the admin theme (server: api/admin/): who may use the CRM (Administration › Accès), the access requests and
   the history of the changes. Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient, type Schemas } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createAdminApi(client: ApiClient) {
  const byEmail = (email: string) => ({ params: { path: { email } } });
  return {
    // ------------------------------------------------------------ Access list
    roles: () => unwrap(client.GET("/api/admin/access/roles")),
    addRole: (body: Schemas["AccessEntryIn"]) => unwrap(client.POST("/api/admin/access/roles", { body })),
    /** Fields left out are kept. */
    updateRole: (email: string, body: Schemas["AccessEntryPatch"]) =>
      unwrap(client.PATCH("/api/admin/access/roles/{email}", { ...byEmail(email), body })),
    removeRole: (email: string) => unwrap(client.DELETE("/api/admin/access/roles/{email}", byEmail(email))),

    // ------------------------------------------------------------ Access requests
    requests: () => unwrap(client.GET("/api/admin/access/requests")),
    grantRequest: (email: string, body: Schemas["AccessGrant"]) =>
      unwrap(client.POST("/api/admin/access/requests/{email}/grant", { ...byEmail(email), body })),
    dismissRequest: (email: string) => unwrap(client.DELETE("/api/admin/access/requests/{email}", byEmail(email))),

    // ------------------------------------------------------------ History
    history: () => unwrap(client.GET("/api/admin/access/history")),
  };
}
