/* API of the admin theme (server: api/admin/): who may use the CRM (Administration › Accès), the invitations and the
   history of the changes. Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient, type Schemas } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createAdminApi(client: ApiClient) {
  const byEmail = (email: string) => ({ params: { path: { email } } });
  return {
    // ------------------------------------------------------------ Access list
    roles: () => unwrap(client.GET("/api/admin/access/roles")),
    /** Invites a new address; the answer says whether the e-mail went out (the invitation is kept either way). */
    invite: (body: Schemas["AccessEntryIn"]) => unwrap(client.POST("/api/admin/access/roles", { body })),
    /** A pending or expired invitation: 7 days again, and its e-mail again. */
    resendInvitation: (email: string) => unwrap(client.POST("/api/admin/access/roles/{email}/invitation", byEmail(email))),
    /** Fields left out are kept. */
    updateRole: (email: string, body: Schemas["AccessEntryPatch"]) =>
      unwrap(client.PATCH("/api/admin/access/roles/{email}", { ...byEmail(email), body })),
    removeRole: (email: string) => unwrap(client.DELETE("/api/admin/access/roles/{email}", byEmail(email))),

    // ------------------------------------------------------------ History
    history: () => unwrap(client.GET("/api/admin/access/history")),
  };
}
