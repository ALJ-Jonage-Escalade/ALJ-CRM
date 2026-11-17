import { describe, expect, it, vi } from "vitest";
import type { ApiFetch } from "../lib/api";
import { ApiError, createApiClient, readUrl } from "../lib/client";
import { json, TEST_ORIGIN } from "../test/harness";
import { createMembersApi, membersRead } from "./members";

describe("members service", () => {
  it("reads the members of a season, the active one when none is given", () => {
    expect(readUrl(membersRead("2025-2026"))).toBe("/api/members?season=2025-2026");
    expect(readUrl(membersRead(""))).toBe("/api/members");
  });

  it("sends the HelloAsso campaign picked for this sync, null for the active one", async () => {
    const api = vi.fn<ApiFetch>(async () => json({ status: "success" }));
    const membersApi = createMembersApi(createApiClient(api, TEST_ORIGIN));
    await membersApi.helloAssoPreview(null);
    await membersApi.helloAssoPreview("adhesion-2026");
    expect(api.mock.calls.map(([url, init]) => [url, init?.method, init?.body])).toEqual([
      [`${TEST_ORIGIN}/api/helloasso/memberships/preview`, "POST", '{"campaign":null}'],
      [`${TEST_ORIGIN}/api/helloasso/memberships/preview`, "POST", '{"campaign":"adhesion-2026"}'],
    ]);
  });

  it("answers the body of a success and throws the server's refusal", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce(json({ seasons: ["2026-2027"] }))
      .mockResolvedValueOnce(json({ detail: "Saison inconnue." }, 404));
    const membersApi = createMembersApi(createApiClient(api, TEST_ORIGIN));
    await expect(membersApi.seasons()).resolves.toEqual({ seasons: ["2026-2027"] });
    await expect(membersApi.seasons()).rejects.toEqual(new ApiError(404, null, "Saison inconnue."));
  });
});
