import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/client";
import { createOfflineStore, type OfflineStore } from "../../lib/store";
import type { Competition, Participant } from "./competitions";
import { createOutbox, logoutWarning, outboxKey, pendingLine, refusalText, replayMessage, type SendChange } from "./outbox";

const UID = "u1";
const LEO: Participant = { adherent_id: 1, nom: "MARTIN", prenom: "Léo", selectionne: true, present: false, updated_at: "t1" };
const ZOE: Participant = { adherent_id: 2, nom: "DURAND", prenom: "Zoé", selectionne: false, updated_at: "t2" };
const COMP: Competition = { id: 10, nom: "Coupe", participants: [LEO, ZOE] };

/** The server: answers the competition with the participant's new updated_at. */
function server(answers: Record<string, (body: object) => unknown> = {}) {
  const sent: { url: string; body: object }[] = [];
  let clock = 100;
  const send: SendChange = vi.fn(async (competitionId, adherentId, body) => {
    const url = `/api/competitions/${competitionId}/participants/${adherentId}`;
    sent.push({ url, body });
    const answer = answers[url]?.(body);
    if (answer instanceof ApiError) throw answer;
    return { id: competitionId, participants: [{ adherent_id: adherentId, updated_at: `t${clock++}` }] };
  });
  return { send, sent };
}

let store: OfflineStore;
let now: number;
beforeEach(async () => {
  store = createOfflineStore({ indexedDB: new IDBFactory() });
  await store.start(UID);
  now = 1000;
});
const clock = () => now++;

describe("outbox", () => {
  it("queues a change, replaces it by key, and cancels it when back to the server's value", async () => {
    const outbox = createOutbox(store, server().send, clock);
    await outbox.queue(UID, COMP, LEO, "selectionne", false);
    expect(outbox.pending(10, 1, "selectionne")).toMatchObject({ value: false, unchanged_since: "t1", label: "MARTIN Léo (Coupe)", queuedAt: 1000 });
    await outbox.queue(UID, COMP, LEO, "present", true);
    await outbox.queue(UID, COMP, LEO, "present", false);  // back to the server's value
    expect([...outbox.changes.value.keys()]).toEqual([outboxKey(10, 1, "selectionne")]);
    expect((await store.queued(UID)).map((e) => e.key)).toEqual(["10:1:selectionne"]);

    await outbox.queue(UID, COMP, ZOE, "selectionne", true);
    await outbox.queue(UID, COMP, LEO, "selectionne", false);  // again: keeps its place in the queue
    expect(outbox.pending(10, 1, "selectionne")!.queuedAt).toBe(1000);
  });

  it("reads what the former page queued and sends it oldest first", async () => {
    // As web/competitions.html wrote it
    await store.queue(UID, { key: "10:2:selectionne", uid: UID, flag: "selectionne", value: true, url: "/api/competitions/10/participants/2", unchanged_since: "t2", label: "DURAND Zoé (Coupe)", queuedAt: 5 });
    await store.queue(UID, { key: "10:1:selectionne", uid: UID, flag: "selectionne", value: false, url: "/api/competitions/10/participants/1", unchanged_since: "t1", label: "MARTIN Léo (Coupe)", queuedAt: 2 });
    const { send, sent } = server();
    const outbox = createOutbox(store, send, clock);
    await outbox.load(UID);
    expect(outbox.changes.value.size).toBe(2);

    expect(await outbox.replay(UID)).toEqual({ done: 2, refused: [], denied: false });
    expect(sent).toEqual([
      { url: "/api/competitions/10/participants/1", body: { selectionne: false, unchanged_since: "t1" } },
      { url: "/api/competitions/10/participants/2", body: { selectionne: true, unchanged_since: "t2" } },
    ]);
    expect(outbox.changes.value.size).toBe(0);
    expect(await store.queued(UID)).toEqual([]);
    expect(await outbox.replay(UID)).toBeNull();  // nothing left
  });

  it("sends a second change of the same competitor with the updated_at the first produced", async () => {
    const { send, sent } = server();
    const outbox = createOutbox(store, send, clock);
    await outbox.queue(UID, COMP, LEO, "selectionne", false);
    await outbox.queue(UID, COMP, LEO, "present", true);
    await outbox.replay(UID);
    expect(sent.map((s) => s.body)).toEqual([{ selectionne: false, unchanged_since: "t1" }, { present: true, unchanged_since: "t100" }]);
  });

  it("drops a refused change with the server's reason and goes on", async () => {
    const { send } = server({
      "/api/competitions/10/participants/1": () => new ApiError(409, "changed", "Modifié entre-temps"),
      "/api/competitions/10/participants/2": () => new ApiError(409, "already_paid", "x"),
    });
    const outbox = createOutbox(store, send, clock);
    await outbox.queue(UID, COMP, LEO, "selectionne", false);
    await outbox.queue(UID, COMP, ZOE, "selectionne", true);
    const result = await outbox.replay(UID);
    expect(result).toEqual({
      done: 2, denied: false,
      refused: ["MARTIN Léo (Coupe) : modifié entre-temps sur un autre appareil", "DURAND Zoé (Coupe) : a payé entre-temps : passez par l'annulation"],
    });
    expect(outbox.changes.value.size).toBe(0);
    expect(await store.queued(UID)).toEqual([]);
    expect(replayMessage(result!)).toBe("⚠️ 2 modifications faites hors ligne refusées : MARTIN Léo (Coupe) : modifié entre-temps sur un autre appareil ; DURAND Zoé (Coupe) : a payé entre-temps : passez par l'annulation");
  });

  it.each([
    [new ApiError(0, "network", "x"), "network down"],
    [new ApiError(503, null, "x"), "server down"],
    [new ApiError(429, null, "x"), "server busy"],
  ])("keeps what is left for later (%s, %s)", async (error) => {
    const { send, sent } = server({ "/api/competitions/10/participants/2": () => error });
    const outbox = createOutbox(store, send, clock);
    await outbox.queue(UID, COMP, LEO, "selectionne", false);
    await outbox.queue(UID, COMP, ZOE, "selectionne", true);
    await outbox.queue(UID, COMP, LEO, "present", true);
    expect(await outbox.replay(UID)).toEqual({ done: 1, refused: [], denied: false });
    expect(sent).toHaveLength(2);  // stopped at the failure
    expect([...outbox.changes.value.keys()]).toEqual(["10:2:selectionne", "10:1:present"]);
    expect((await store.queued(UID)).length).toBe(2);
  });

  it("stops on a lost role (401/403) and says so", async () => {
    const { send } = server({ "/api/competitions/10/participants/1": () => new ApiError(403, null, "x") });
    const outbox = createOutbox(store, send, clock);
    await outbox.queue(UID, COMP, LEO, "selectionne", false);
    await outbox.queue(UID, COMP, ZOE, "selectionne", true);
    expect(await outbox.replay(UID)).toEqual({ done: 0, refused: [], denied: true });
  });

  it("refuses an entry it does not allow, without sending it", async () => {
    await store.queue(UID, { key: "x", uid: UID, flag: "statut_paiement", value: "paye", url: "/api/competitions/10/participants/1", label: "MARTIN Léo", queuedAt: 1 });
    await store.queue(UID, { key: "y", uid: UID, flag: "selectionne", value: true, url: "/api/competitions/10", label: "Coupe", queuedAt: 2 });
    const { send, sent } = server();
    const outbox = createOutbox(store, send, clock);
    await outbox.load(UID);
    const result = await outbox.replay(UID);
    expect(result!.refused).toEqual(["MARTIN Léo : modification non valide, non envoyée", "Coupe : modification non valide, non envoyée"]);
    expect(sent).toEqual([]);
    expect(await store.queued(UID)).toEqual([]);
  });

  it("keeps a change made again while the first one was being sent", async () => {
    let release!: () => void;
    const send: SendChange = vi.fn(() => new Promise<Competition>((resolve) => (release = () => resolve({ id: 10, participants: [] }))));
    const outbox = createOutbox(store, send, clock);
    await outbox.queue(UID, COMP, LEO, "present", true);
    const replay = outbox.replay(UID);
    await vi.waitFor(() => expect(send).toHaveBeenCalled());
    await outbox.queue(UID, COMP, LEO, "present", true);  // changed again (same value, new entry)
    expect(await outbox.replay(UID)).toBeNull();  // already sending
    release();
    await replay;
    expect(outbox.pending(10, 1, "present")).toBeDefined();
    expect((await store.queued(UID)).map((e) => e.key)).toEqual(["10:1:present"]);
  });

  it("forgets everything on clear, and a replay running then stops", async () => {
    let release!: () => void;
    const send: SendChange = vi.fn(() => new Promise<Competition>((resolve) => (release = () => resolve({ id: 10, participants: [] }))));
    const outbox = createOutbox(store, send, clock);
    await outbox.queue(UID, COMP, LEO, "selectionne", false);
    await outbox.queue(UID, COMP, ZOE, "selectionne", true);
    const replay = outbox.replay(UID);
    await vi.waitFor(() => expect(send).toHaveBeenCalled());
    outbox.forget();
    await store.clearAll();
    release();
    expect(await replay).toBeNull();
    expect(send).toHaveBeenCalledTimes(1);
    expect(outbox.changes.value.size).toBe(0);
    expect(await store.queued(UID)).toEqual([]);
  });

  it("only reads this user's changes", async () => {
    const outbox = createOutbox(store, server().send, clock);
    await outbox.queue(UID, COMP, LEO, "selectionne", false);
    await outbox.load("other");
    expect(outbox.changes.value.size).toBe(0);
    await outbox.load(null);
    expect(outbox.changes.value.size).toBe(0);
  });

  it("words the messages", () => {
    expect(refusalText(new ApiError(404, null, "x"))).toBe("n'est plus inscrit à cette compétition");
    expect(refusalText(new ApiError(409, "competition_closed", "x"))).toBe("compétition archivée");
    expect(refusalText(new ApiError(400, null, "Refusé"))).toBe("Refusé");
    expect(logoutWarning(1)).toBe("1 modification faite hors ligne pas encore envoyée sera perdue. Se déconnecter ?");
    expect(logoutWarning(2)).toBe("2 modifications faites hors ligne pas encore envoyées seront perdues. Se déconnecter ?");
    expect(pendingLine(0)).toBe("");
    expect(pendingLine(3)).toBe(" · ⏳ 3 modifications à envoyer");
    expect(replayMessage({ done: 1, refused: [], denied: false })).toBe("☁️ Modifications faites hors ligne envoyées.");
  });
});
