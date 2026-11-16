import { describe, expect, it } from "vitest";
import { recordingClient } from "../test/harness";
import { createActivitiesApi } from "./activities";

describe("activities service", () => {
  it("sends each planning and attendance request to its route", async () => {
    const { client, sent } = recordingClient();
    const activitiesApi = createActivitiesApi(client);
    await activitiesApi.planning();
    await activitiesApi.saveSlot({ id: 3, jour: "Lundi", groupe: "Adultes" });
    await activitiesApi.removeSlot(12);
    await activitiesApi.planningFile("list");
    await activitiesApi.presenceConfig();
    await activitiesApi.presenceFile({ variant: "cours", season: "2026-2027" });
    expect(sent.map(({ method, path }) => `${method} ${path}`)).toEqual([
      "GET /api/planning",
      "POST /api/planning/item",
      "DELETE /api/planning/item/12",
      "GET /api/planning/export?mode=list",
      "GET /api/presence/config",
      "POST /api/presence/export",
    ]);
    expect(sent[1]?.body).toEqual({ id: 3, jour: "Lundi", groupe: "Adultes" });
    expect(sent[5]?.body).toEqual({ variant: "cours", season: "2026-2027" });
  });

  it("returns the export call itself, for saveExport()", async () => {
    const { client } = recordingClient();
    const answer = await createActivitiesApi(client).planningFile("grid");
    expect(answer.response.ok).toBe(true);
    expect(answer.data).toBeInstanceOf(Blob);
  });
});
