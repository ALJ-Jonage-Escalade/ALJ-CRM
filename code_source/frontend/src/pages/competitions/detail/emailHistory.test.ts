import { describe, expect, it } from "vitest";
import { failedCount, isInternal, KIND_LABELS, lastSendState, type EmailLog, type EmailLogEntry } from "./emailHistory";

const recipient = (member_id: number | null, email: string, status: "sent" | "failed" = "sent") => ({
  member_id,
  email,
  name: "",
  status,
  error: status === "failed" ? "refusé" : null,
});

const entry = (at: string, recipients: EmailLogEntry["recipients"], kind: EmailLogEntry["kind"] = "competition_email"): EmailLogEntry => ({
  at,
  author: "coach@alj.example",
  kind,
  template: "",
  subject: "Rappel",
  competition_ids: [7],
  member_ids: [],
  recipients,
});

const log: EmailLog = {
  entries: [
    entry("2026-11-03T09:00:00+00:00", [recipient(null, "club@alj.example")], "competition_all_paid"),
    entry("2026-11-02T09:00:00+00:00", [recipient(1, "ana@example.org", "failed"), recipient(2, "bob@example.org")]),
    entry("2026-11-01T09:00:00+00:00", [recipient(1, "ana@example.org"), recipient(null, "Guest@Example.org")]),
  ],
  summary: {
    last_competitor_email_at: "2026-11-02T09:00:00+00:00",
    competitors: [
      { member_id: 1, email: "ana@example.org", last_sent_at: "2026-11-01T09:00:00+00:00", last_failed: true },
      { member_id: 2, email: "bob@example.org", last_sent_at: "2026-11-02T09:00:00+00:00", last_failed: false },
      { member_id: 3, email: "cleo@example.org", last_sent_at: null, last_failed: false },
      { member_id: null, email: "guest@example.org", last_sent_at: "2026-11-01T09:00:00+00:00", last_failed: false },
    ],
  },
};
const loaded = { log, failed: false };

describe("last send", () => {
  it("never says « none » without a log: unavailable once reading failed, nothing while loading", () => {
    expect(lastSendState({ log: null, failed: true })).toEqual({ kind: "unavailable" });
    expect(lastSendState({ log: null, failed: false })).toEqual({ kind: "loading" });
  });
});

describe("history", () => {
  it("last send to the competitors", () => {
    expect(lastSendState(loaded)).toEqual({ kind: "date", at: "2026-11-02T09:00:00+00:00" });
    expect(lastSendState({ log: { entries: [], summary: { last_competitor_email_at: null, competitors: [] } }, failed: false })).toEqual({
      kind: "none",
    });
  });

  it("labels, internal kinds and failures", () => {
    expect(KIND_LABELS.competition_all_paid).toMatch(/^Interne/);
    expect(isInternal("results_batch")).toBe(true);
    expect(isInternal("competition_email")).toBe(false);
    expect(log.entries.map(failedCount)).toEqual([0, 1, 0]);
  });
});
