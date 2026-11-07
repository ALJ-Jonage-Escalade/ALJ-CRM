/* API of the competitions theme (server: api/competitions/): competitions, their participants, coaches, HelloAsso
   payments and MyCompet results. Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient, type Schemas } from "../lib/client";
import type { MemberStatus } from "../pages/adherents/members";
import { ARCHIVED, PREPARING } from "../pages/competitions/competitions";

/** Club searched on the MyCompet results pages. */
const RESULTS_CLUB = "JONAGE";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createCompetitionsApi(client: ApiClient) {
  const competition = (competitionId: number) => ({ params: { path: { competition_id: competitionId } } });
  const participant = (competitionId: number, adherentId: number) => ({
    params: { path: { competition_id: competitionId, adherent_id: adherentId } },
  });

  return {
    // ------------------------------------------------------------ Competitions
    create: (body: Schemas["CompetitionCreate"]) => unwrap(client.POST("/api/competitions", { body })),
    update: (competitionId: number, body: Schemas["CompetitionUpdate"]) =>
      unwrap(client.PATCH("/api/competitions/{competition_id}", { ...competition(competitionId), body })),
    setArchived: (competitionId: number, archived: boolean) =>
      unwrap(
        client.PATCH("/api/competitions/{competition_id}", {
          ...competition(competitionId),
          body: { statut: archived ? ARCHIVED : PREPARING },
        }),
      ),
    remove: (competitionId: number) => unwrap(client.DELETE("/api/competitions/{competition_id}", competition(competitionId))),
    archivePast: () => unwrap(client.POST("/api/competitions/archive-past")),
    /** Scrapes MyCompet FFME for competition title and metadata from its ID number. */
    lookupFfme: (idFfme: string) =>
      unwrap(client.GET("/api/competitions/lookup-ffme/{id_ffme}", { params: { path: { id_ffme: idFfme } } })),
    /** List of the competitors (Excel), for saveExport(). */
    competitorsExcel: (competitionId: number) =>
      client.GET("/api/competitions/{competition_id}/export-excel", { ...competition(competitionId), parseAs: "blob" }),
    /** List of the competitors (PDF; the printable HTML page when the server has no WeasyPrint), for saveExport(). */
    competitorsPdf: (competitionId: number) =>
      client.GET("/api/competitions/{competition_id}/export-pdf", { ...competition(competitionId), parseAs: "blob" }),
    /** url "": the server looks for the competition's page on MyCompet itself. */
    fetchResults: (competitionId: number, url: string) =>
      unwrap(
        client.POST("/api/competitions/{comp_id}/fetch-results", {
          params: { path: { comp_id: String(competitionId) } },
          body: { url, club: RESULTS_CLUB },
        }),
      ),

    // ------------------------------------------------------------ MyCompet results of every competition (Paramètres)
    resultsSettings: () => unwrap(client.GET("/api/settings/competitions-results")),
    /** windowDays: search window of the daily batch (days since the competition ended), unchanged when omitted. */
    saveResultsSettings: (notificationEmail: string, windowDays?: number) =>
      unwrap(
        client.POST("/api/settings/competitions-results", {
          body: { notification_email: notificationEmail, ...(windowDays === undefined ? {} : { window_days: windowDays }) },
        }),
      ),
    /** The daily batch run now, results already fetched included. */
    fetchAllResults: () => unwrap(client.POST("/api/competitions/cron/fetch-results", { params: { query: { force: true } } })),

    // ------------------------------------------------------------ Participants
    /** Adds a member to the list as a competitor (also restores a withdrawn one). */
    addParticipant: (competitionId: number, adherentId: number) =>
      unwrap(
        client.POST("/api/competitions/{competition_id}/participants", {
          ...competition(competitionId),
          body: { adherent_id: adherentId, selectionne: true },
        }),
      ),
    /** Adds the members of the « Compétition » group not on the list yet, only those at one of `statuses`. */
    loadGroup: (competitionId: number, statuses: readonly MemberStatus[]) =>
      unwrap(
        client.POST("/api/competitions/{competition_id}/load-group", {
          params: { path: { competition_id: competitionId }, query: { status: [...statuses] } },
        }),
      ),
    updateParticipant: (competitionId: number, adherentId: number, body: Schemas["ParticipantUpdate"]) =>
      unwrap(
        client.PATCH("/api/competitions/{competition_id}/participants/{adherent_id}", { ...participant(competitionId, adherentId), body }),
      ),
    removeParticipant: (competitionId: number, adherentId: number) =>
      unwrap(client.DELETE("/api/competitions/{competition_id}/participants/{adherent_id}", participant(competitionId, adherentId))),
    withdraw: (competitionId: number, adherentId: number, body: Schemas["ParticipantCancel"]) =>
      unwrap(
        client.POST("/api/competitions/{competition_id}/participants/{adherent_id}/cancel", {
          ...participant(competitionId, adherentId),
          body,
        }),
      ),
    payManually: (competitionId: number, adherentId: number, amount: number) =>
      unwrap(
        client.POST("/api/competitions/{competition_id}/participants/{adherent_id}/manual-payment", {
          ...participant(competitionId, adherentId),
          body: { montant: amount },
        }),
      ),

    // ------------------------------------------------------------ Coaches
    createCoach: (nom: string) => unwrap(client.POST("/api/coaches", { body: { nom } })),
    renameCoach: (coachId: number, nom: string) =>
      unwrap(client.PUT("/api/coaches/{coach_id}", { params: { path: { coach_id: coachId } }, body: { nom } })),
    removeCoach: (coachId: number) => unwrap(client.DELETE("/api/coaches/{coach_id}", { params: { path: { coach_id: coachId } } })),

    // ------------------------------------------------------------ HelloAsso payments
    linkPayment: (itemId: number, body: Schemas["ItemLink"]) =>
      unwrap(client.PUT("/api/helloasso/items/{id_item}/link", { params: { path: { id_item: itemId } }, body })),
    ignorePayment: (itemId: number, body: Schemas["ItemIgnore"]) =>
      unwrap(client.PUT("/api/helloasso/items/{id_item}/ignore", { params: { path: { id_item: itemId } }, body })),
  };
}
