import { describe, expect, it } from "vitest";
import { recordingClient } from "../test/harness";
import { createKeysApi } from "./keys";

describe("keys service", () => {
  it("addresses each key and assignment by its id, with the server's field names", async () => {
    const { client, sent } = recordingClient();
    const keysApi = createKeysApi(client);
    await keysApi.list();
    await keysApi.add("A12");
    await keysApi.assign(3, { user_id: 7, given_on: "2026-11-16" });
    await keysApi.giveBack(3, { returned_on: "2026-11-20", comment: "fin de saison" });
    await keysApi.rename(3, "A13");
    await keysApi.archive(3, { archived_on: "2026-11-21", comment: "perdue" });
    await keysApi.restore(3, "retrouvée");
    await keysApi.history(3);
    await keysApi.correctAssignment(9, { given_on: "2026-11-15", returned_on: null });
    await keysApi.deleteAssignment(9);
    expect(sent.map(({ method, path, body }) => [`${method} ${path}`, body])).toEqual([
      ["GET /api/keys", undefined],
      ["POST /api/keys", { code: "A12" }],
      ["POST /api/keys/3/assignments", { user_id: 7, given_on: "2026-11-16" }],
      ["POST /api/keys/3/return", { returned_on: "2026-11-20", comment: "fin de saison" }],
      ["PATCH /api/keys/3", { code: "A13" }],
      ["POST /api/keys/3/archive", { archived_on: "2026-11-21", comment: "perdue" }],
      ["POST /api/keys/3/restore", { comment: "retrouvée" }],
      ["GET /api/keys/3/history", undefined],
      ["PATCH /api/key-assignments/9", { given_on: "2026-11-15", returned_on: null }],
      ["DELETE /api/key-assignments/9", undefined],
    ]);
  });
});
