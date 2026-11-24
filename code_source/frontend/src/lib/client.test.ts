import { json } from "../test/harness";
import { describe, expect, it, vi } from "vitest";
import { createApiFetch } from "./api";
import { ApiError, createApiClient, errorFromBody, NETWORK_MESSAGE, readUrl, unwrap } from "./client";

const BASE = "http://alj.test";

/** The URL a fetch was called with, whatever its form. */
const href = (url: RequestInfo | URL): string => (url instanceof Request ? url.url : url.toString());

/** The client over the real apiFetch (token, retry) over a fake network. */
function setup(answer: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const network = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => answer(href(url), init ?? {}));
  const client = createApiClient(
    createApiFetch(async () => "token-1", network),
    BASE,
  );
  const sent = (i = 0) => {
    const [url, init] = network.mock.calls[i]!;
    return { url: href(url), init: init!, headers: new Headers(init!.headers) };
  };
  return { client, network, sent };
}

describe("createApiClient", () => {
  it("sends the ID token and returns the typed body", async () => {
    const { client, sent } = setup(() => json({ email: "a@b.c", role: "admin" }));
    const me = await unwrap(client.GET("/api/me"));
    expect(me).toEqual({ email: "a@b.c", role: "admin" });
    expect(sent().url).toBe(`${BASE}/api/me`);
    expect(sent().headers.get("Authorization")).toBe("Bearer token-1");
  });

  it("sends JSON bodies and query parameters", async () => {
    const { client, sent } = setup(() => json({ status: "success", notification_email: "n@x.fr", window_days: 30 }));
    await unwrap(client.POST("/api/settings/competitions-results", { body: { notification_email: "n@x.fr" } }));
    expect(sent().init.method).toBe("POST");
    expect(sent().headers.get("Content-Type")).toBe("application/json");
    expect(JSON.parse(sent().init.body as string)).toEqual({ notification_email: "n@x.fr" });

    await unwrap(client.POST("/api/cloud-db/sync", { params: { query: { force: true } } })).catch(() => {});
    expect(sent(1).url).toBe(`${BASE}/api/cloud-db/sync?force=true`);
  });

  it("maps the API's error body", async () => {
    const { client } = setup(() => json({ status: "error", message: "Adresse e-mail de notification invalide.", code: "bad_email" }, 400));
    const err = await unwrap(client.POST("/api/settings/competitions-results", { body: { notification_email: "x" } })).catch(
      (e: unknown) => e,
    );
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 400, code: "bad_email", message: "Adresse e-mail de notification invalide." });
  });

  it("maps a network failure", async () => {
    const { client } = setup(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(unwrap(client.GET("/api/cloud-db/status"))).rejects.toMatchObject({
      status: 0,
      code: "network",
      message: NETWORK_MESSAGE,
    });
  });

  it("maps a server error without a JSON body", async () => {
    const { client } = setup(() => new Response("<html>Bad gateway</html>", { status: 502 }));
    await expect(unwrap(client.GET("/api/cloud-db/status"))).rejects.toMatchObject({
      status: 502,
      code: null,
      message: "Le serveur ne répond pas correctement (erreur 502).",
    });
  });
});

describe("errorFromBody", () => {
  it.each([
    [{ detail: "Compétition introuvable" }, 404, null, "Compétition introuvable"],
    [
      { detail: [{ loc: ["body", "notification_email"], msg: "x" }, { loc: ["body", "notification_email"] }] },
      422,
      "validation",
      "Données refusées par le serveur (notification_email).",
    ],
    [{ detail: [] }, 422, "validation", "Données refusées par le serveur."],
    [null, 401, null, "Session refusée par le serveur : reconnectez-vous."],
    [{ status: "error", message: "" }, 403, null, "Action non autorisée pour votre rôle."],
    ["texte", 500, null, "Le serveur ne répond pas correctement (erreur 500)."],
  ])("%j (%i)", (body, status, code, message) => {
    expect(errorFromBody(status, body)).toMatchObject({ status, code, message });
  });
});

describe("readUrl", () => {
  it("writes the query of a read as the url the offline copies are keyed by", () => {
    expect(readUrl({ path: "/api/members" })).toBe("/api/members");
    expect(readUrl({ path: "/api/members", query: { season: "2025-2026" } })).toBe("/api/members?season=2025-2026");
    expect(readUrl({ path: "/api/members", query: { season: null } })).toBe("/api/members");
    expect(readUrl({ path: "/api/competition-members", query: { status: ["Terminé", "Validé"] } })).toBe(
      "/api/competition-members?status=Termin%C3%A9&status=Valid%C3%A9",
    );
  });
});
