import { describe, expect, it } from "vitest";
import { competitorContact, entriesFor, failedCount, isInternal, KIND_LABELS, type EmailLog, type EmailLogEntry } from "./emailHistory";

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
    competitors: [
      { member_id: 1, email: "ana@example.org", last_sent_at: "2026-11-01T09:00:00+00:00", last_failed: true },
      { member_id: 2, email: "bob@example.org", last_sent_at: "2026-11-02T09:00:00+00:00", last_failed: false },
      { member_id: 3, email: "cleo@example.org", last_sent_at: null, last_failed: false },
      { member_id: null, email: "guest@example.org", last_sent_at: "2026-11-01T09:00:00+00:00", last_failed: false },
    ],
  },
};
const loaded = { log, failed: false };

describe("competitor contact", () => {
  it.each([
    ["last send failed", { adherent_id: 1, email: "ana@example.org" }, { kind: "failed", at: "2026-11-01T09:00:00+00:00" }],
    ["sent", { adherent_id: 2, email: "x@example.org" }, { kind: "date", at: "2026-11-02T09:00:00+00:00" }],
    ["never e-mailed", { adherent_id: 3, email: "cleo@example.org" }, { kind: "none" }],
    ["no member id: by address", { adherent_id: null, email: "GUEST@example.org" }, { kind: "date", at: "2026-11-01T09:00:00+00:00" }],
    ["not in the summary", { adherent_id: 9, email: "" }, { kind: "none" }],
  ])("%s", (_name, row, state) => {
    expect(competitorContact(loaded, row)).toEqual(state);
  });

  it("never says « none » without a log: unavailable once reading failed, nothing while loading", () => {
    const row = { adherent_id: 3, email: "cleo@example.org" };
    expect(competitorContact({ log: null, failed: true }, row)).toEqual({ kind: "unavailable" });
    expect(competitorContact({ log: null, failed: false }, row)).toEqual({ kind: "loading" });
  });
});

describe("history", () => {
  it("the sends that included one competitor, newest first", () => {
    expect(entriesFor(log.entries, { adherent_id: 1, email: "ana@example.org" }).map((e) => e.at)).toEqual([
      "2026-11-02T09:00:00+00:00",
      "2026-11-01T09:00:00+00:00",
    ]);
    expect(entriesFor(log.entries, { adherent_id: null, email: "guest@example.org" })).toHaveLength(1);
  });

  it("labels, internal kinds and failures", () => {
    expect(KIND_LABELS.competition_all_paid).toMatch(/^Interne/);
    expect(isInternal("results_batch")).toBe(true);
    expect(isInternal("competition_email")).toBe(false);
    expect(log.entries.map(failedCount)).toEqual([0, 1, 0]);
  });
});
