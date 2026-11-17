import { describe, expect, it } from "vitest";
import { recordingClient } from "../test/harness";
import { createCompetitionsApi } from "./competitions";

describe("competitions service", () => {
  it("archives with « close » and puts back in preparation", async () => {
    const { client, sent } = recordingClient();
    const competitionsApi = createCompetitionsApi(client);
    await competitionsApi.setArchived(4, true);
    await competitionsApi.setArchived(4, false);
    expect(sent).toEqual([
      { method: "PATCH", path: "/api/competitions/4", body: { statut: "close" } },
      { method: "PATCH", path: "/api/competitions/4", body: { statut: "en_preparation" } },
    ]);
  });

  it("searches the club's MyCompet results, from the page given or by itself", async () => {
    const { client, sent } = recordingClient();
    const competitionsApi = createCompetitionsApi(client);
    await competitionsApi.fetchResults(4, "");
    await competitionsApi.fetchResults(4, "https://mycompet.ffme.fr/resultat/123");
    await competitionsApi.fetchAllResults();
    expect(sent).toEqual([
      { method: "POST", path: "/api/competitions/4/fetch-results", body: { url: "", club: "JONAGE" } },
      { method: "POST", path: "/api/competitions/4/fetch-results", body: { url: "https://mycompet.ffme.fr/resultat/123", club: "JONAGE" } },
      { method: "POST", path: "/api/competitions/cron/fetch-results?force=true", body: undefined },
    ]);
  });

  it("keeps the batch's search window unless one is given", async () => {
    const { client, sent } = recordingClient();
    const competitionsApi = createCompetitionsApi(client);
    await competitionsApi.saveResultsSettings("resultats@example.org");
    await competitionsApi.saveResultsSettings("resultats@example.org", 0);
    expect(sent.map((request) => request.body)).toEqual([
      { notification_email: "resultats@example.org" },
      { notification_email: "resultats@example.org", window_days: 0 },
    ]);
  });

  it("adds a member as a selected competitor, loads the group at the statuses given, pays by hand", async () => {
    const { client, sent } = recordingClient();
    const competitionsApi = createCompetitionsApi(client);
    await competitionsApi.addParticipant(4, 17);
    await competitionsApi.loadGroup(4, ["Validé", "En cours"]);
    await competitionsApi.payManually(4, 17, 12.5);
    await competitionsApi.withdraw(4, 17, { mode: "withdraw", note: "blessure" });
    await competitionsApi.removeParticipant(4, 17);
    expect(sent).toEqual([
      { method: "POST", path: "/api/competitions/4/participants", body: { adherent_id: 17, selectionne: true } },
      { method: "POST", path: "/api/competitions/4/load-group?status=Validé&status=En cours", body: undefined },
      { method: "POST", path: "/api/competitions/4/participants/17/manual-payment", body: { montant: 12.5 } },
      { method: "POST", path: "/api/competitions/4/participants/17/cancel", body: { mode: "withdraw", note: "blessure" } },
      { method: "DELETE", path: "/api/competitions/4/participants/17", body: undefined },
    ]);
  });

  it("addresses coaches, HelloAsso items and FFME lookups by their id", async () => {
    const { client, sent } = recordingClient();
    const competitionsApi = createCompetitionsApi(client);
    await competitionsApi.createCoach("Hagrid");
    await competitionsApi.renameCoach(2, "Rubeus Hagrid");
    await competitionsApi.removeCoach(2);
    await competitionsApi.lookupFfme("2026-123");
    await competitionsApi.archivePast();
    expect(sent.map(({ method, path, body }) => [`${method} ${path}`, body])).toEqual([
      ["POST /api/coaches", { nom: "Hagrid" }],
      ["PUT /api/coaches/2", { nom: "Rubeus Hagrid" }],
      ["DELETE /api/coaches/2", undefined],
      ["GET /api/competitions/lookup-ffme/2026-123", undefined],
      ["POST /api/competitions/archive-past", undefined],
    ]);
  });

  it("returns the export calls themselves, for saveExport()", async () => {
    const { client, sent } = recordingClient();
    const competitionsApi = createCompetitionsApi(client);
    const excel = await competitionsApi.competitorsExcel(4);
    await competitionsApi.competitorsPdf(4);
    expect(excel.data).toBeInstanceOf(Blob);
    expect(sent.map((request) => request.path)).toEqual(["/api/competitions/4/export-excel", "/api/competitions/4/export-pdf"]);
  });
});
