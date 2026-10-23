import { describe, expect, it } from "vitest";
import { deployedVersion } from "./version";

const answer = (body: unknown, status = 200) => async () => new Response(JSON.stringify(body), { status });

describe("deployedVersion", () => {
  it("reads the app version deployed", async () => {
    expect(await deployedVersion(answer({ app_version: "2.8.0" }))).toBe("2.8.0");
  });

  it.each([
    ["an error status", answer({ app_version: "2.8.0" }, 503)],
    ["no version", answer({})],
    ["offline", async () => { throw new TypeError("Failed to fetch"); }],
  ])("is null on %s", async (_case, fetchImpl) => {
    expect(await deployedVersion(fetchImpl)).toBeNull();
  });
});
