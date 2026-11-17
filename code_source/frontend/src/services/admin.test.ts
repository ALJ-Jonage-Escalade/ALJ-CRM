import { describe, expect, it } from "vitest";
import { recordingClient } from "../test/harness";
import { createAdminApi } from "./admin";

describe("admin service", () => {
  it("addresses each access entry by its e-mail", async () => {
    const { client, sent } = recordingClient();
    const adminApi = createAdminApi(client);
    await adminApi.roles();
    await adminApi.invite({ email: "luna@example.org", role: "coach" });
    await adminApi.resendInvitation("luna@example.org");
    await adminApi.updateRole("luna@example.org", { role: "admin" });
    await adminApi.removeRole("luna@example.org");
    await adminApi.history();
    expect(sent.map(({ method, path, body }) => [`${method} ${path}`, body])).toEqual([
      ["GET /api/admin/access/roles", undefined],
      ["POST /api/admin/access/roles", { email: "luna@example.org", role: "coach" }],
      ["POST /api/admin/access/roles/luna@example.org/invitation", undefined],
      ["PATCH /api/admin/access/roles/luna@example.org", { role: "admin" }],
      ["DELETE /api/admin/access/roles/luna@example.org", undefined],
      ["GET /api/admin/access/history", undefined],
    ]);
  });
});
