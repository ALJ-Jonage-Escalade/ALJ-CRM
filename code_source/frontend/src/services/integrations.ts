/* API of the integrations theme (server: api/integrations/): the Google account used for e-mails, the server's
   cache of the Firestore data and the HelloAsso payments download. Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createIntegrationsApi(client: ApiClient) {
  return {
    // ------------------------------------------------------------ Google account
    googleStatus: () => unwrap(client.GET("/api/auth/google/status")),
    testGoogle: () => unwrap(client.POST("/api/auth/google/test")),
    updateGoogleToken: (refreshToken: string) =>
      unwrap(client.POST("/api/auth/google/update-token", { body: { refresh_token: refreshToken } })),

    // ------------------------------------------------------------ Cache of the Firestore data
    cacheStatus: () => unwrap(client.GET("/api/cloud-db/status")),
    /** full: rebuilds the whole cache, else only what changed. */
    syncCache: (full: boolean) => unwrap(client.POST("/api/cloud-db/sync", { params: { query: { force: full } } })),

    // ------------------------------------------------------------ HelloAsso
    /** Downloads the new HelloAsso payments and links the ones it recognises. */
    syncHelloAsso: () => unwrap(client.POST("/api/helloasso/sync")),
  };
}
