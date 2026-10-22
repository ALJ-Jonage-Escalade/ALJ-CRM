import { describe, expect, it, vi } from "vitest";
import { createApiFetch } from "./api";

function recorder(statuses: number[]) {
  const calls: { url: string; headers: Headers; method?: string }[] = [];
  const fetchImpl = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), headers: new Headers(init?.headers), method: init?.method });
    return new Response(null, { status: statuses[calls.length - 1] ?? 200 });
  });
  return { calls, fetchImpl: fetchImpl as unknown as typeof fetch };
}

describe("createApiFetch", () => {
  it("sends the ID token and keeps the caller's options", async () => {
    const { calls, fetchImpl } = recorder([200]);
    const api = createApiFetch(async () => "token-1", fetchImpl);
    const res = await api("/api/me", { method: "POST", headers: { "Content-Type": "application/json" } });
    expect(res.status).toBe(200);
    expect(calls).toHaveLength(1);
    expect(calls[0]?.method).toBe("POST");
    expect(calls[0]?.headers.get("Authorization")).toBe("Bearer token-1");
    expect(calls[0]?.headers.get("Content-Type")).toBe("application/json");
  });

  it("sends no Authorization header when signed out, and does not retry a 401", async () => {
    const { calls, fetchImpl } = recorder([401]);
    const api = createApiFetch(async () => null, fetchImpl);
    expect((await api("/api/me")).status).toBe(401);
    expect(calls).toHaveLength(1);
    expect(calls[0]?.headers.has("Authorization")).toBe(false);
  });

  it("retries once with a refreshed token on 401", async () => {
    const { calls, fetchImpl } = recorder([401, 200]);
    const getToken = vi.fn(async (force: boolean) => (force ? "fresh" : "stale"));
    const api = createApiFetch(getToken, fetchImpl);
    expect((await api("/api/me")).status).toBe(200);
    expect(getToken.mock.calls).toEqual([[false], [true]]);
    expect(calls.map((c) => c.headers.get("Authorization"))).toEqual(["Bearer stale", "Bearer fresh"]);
  });

  it("returns the second 401 instead of looping", async () => {
    const { calls, fetchImpl } = recorder([401, 401]);
    const api = createApiFetch(async () => "t", fetchImpl);
    expect((await api("/api/me")).status).toBe(401);
    expect(calls).toHaveLength(2);
  });

  it("does not retry other errors", async () => {
    const { calls, fetchImpl } = recorder([403]);
    const api = createApiFetch(async () => "t", fetchImpl);
    expect((await api("/api/email-status")).status).toBe(403);
    expect(calls).toHaveLength(1);
  });
});
