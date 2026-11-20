/* API of the FFME theme (server: api/ffme/): the licence export for the federation and the import of its answer.
   Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient, type Schemas } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createFfmeApi(client: ApiClient) {
  return {
    /** Counts of the CSV that exportFile(includeFinished) would produce. */
    stats: (includeFinished: boolean) => unwrap(client.GET("/api/ffme/stats", { params: { query: { include_termine: includeFinished } } })),
    /** FFME CSV file, for saveExport(). */
    exportFile: (includeFinished: boolean) =>
      client.GET("/api/ffme/export", { params: { query: { include_termine: includeFinished } }, parseAs: "blob" }),
    /** Matches the federation's file (and the office's manual matches) against the members and lists the changes, writes nothing. */
    preview: (body: Schemas["FfmePreviewRequest"]) => unwrap(client.POST("/api/ffme/preview", { body })),
    import: (body: Schemas["FfmeImportRequest"]) => unwrap(client.POST("/api/ffme/import", { body })),
  };
}
