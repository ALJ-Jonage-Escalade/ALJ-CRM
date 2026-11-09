/* API of the keys theme (server: api/keys/): the club keys of the climbing wall, Outils › Clés.
   Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient, type Schemas } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createKeysApi(client: ApiClient) {
  return {
    list: () => unwrap(client.GET("/api/keys")),
    add: (code: string) => unwrap(client.POST("/api/keys", { body: { code } })),
    assign: (keyId: number, body: Schemas["KeyAssignmentIn"]) =>
      unwrap(client.POST("/api/keys/{key_id}/assignments", { params: { path: { key_id: keyId } }, body })),
    giveBack: (keyId: number, body: Schemas["KeyReturnIn"]) =>
      unwrap(client.POST("/api/keys/{key_id}/return", { params: { path: { key_id: keyId } }, body })),
    rename: (keyId: number, code: string) =>
      unwrap(client.PATCH("/api/keys/{key_id}", { params: { path: { key_id: keyId } }, body: { code } })),
    history: (keyId: number) => unwrap(client.GET("/api/keys/{key_id}/history", { params: { path: { key_id: keyId } } })),
    correctAssignment: (assignmentId: number, body: Schemas["KeyAssignmentPatch"]) =>
      unwrap(client.PATCH("/api/key-assignments/{assignment_id}", { params: { path: { assignment_id: assignmentId } }, body })),
    deleteAssignment: (assignmentId: number) =>
      unwrap(client.DELETE("/api/key-assignments/{assignment_id}", { params: { path: { assignment_id: assignmentId } } })),
  };
}
