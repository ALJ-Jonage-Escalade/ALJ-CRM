/* API of the activities theme (server: api/activities/): the weekly planning and the attendance sheets.
   Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient, type Schemas } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createActivitiesApi(client: ApiClient) {
  return {
    // ------------------------------------------------------------ Planning
    planning: () => unwrap(client.GET("/api/planning")),
    /** Creates the slot, or updates it when it has an id. */
    saveSlot: (body: Schemas["PlanningSlotUpdate"]) => unwrap(client.POST("/api/planning/item", { body })),
    removeSlot: (slotId: number) => unwrap(client.DELETE("/api/planning/item/{item_id}", { params: { path: { item_id: slotId } } })),
    /** Excel file, for saveExport(). */
    planningFile: (mode: "grid" | "list") => client.GET("/api/planning/export", { params: { query: { mode } }, parseAs: "blob" }),

    // ------------------------------------------------------------ Attendance sheets
    presenceConfig: () => unwrap(client.GET("/api/presence/config")),
    /** Excel file, for saveExport(). */
    presenceFile: (body: Schemas["PresenceExportRequest"]) => client.POST("/api/presence/export", { body, parseAs: "blob" }),
  };
}
