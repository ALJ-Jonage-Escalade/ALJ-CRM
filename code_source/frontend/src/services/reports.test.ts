import { describe, expect, it } from "vitest";
import { recordingClient } from "../test/harness";
import { createReportsApi } from "./reports";

describe("reports service", () => {
  it("asks the map for the season given, the statistics for every season", async () => {
    const { client, sent } = recordingClient();
    const reportsApi = createReportsApi(client);
    await reportsApi.mapPoints("active");
    await reportsApi.memberStats();
    expect(sent.map(({ method, path }) => `${method} ${path}`)).toEqual([
      "GET /api/reports/map-points?season=active",
      "GET /api/reports/member-stats",
    ]);
  });
});
