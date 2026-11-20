import { describe, expect, it } from "vitest";
import { failedCount, filterEntries, isInternal, KIND_LABELS, type EmailLogEntry } from "./emailLog";

const entry = (fields: Partial<EmailLogEntry>): EmailLogEntry => ({
  at: "2026-11-01T09:00:00+00:00",
  author: "coach@alj.example",
  kind: "competition_email",
  template: "",
  subject: "",
  competition_ids: [],
  member_ids: [],
  recipients: [],
  ...fields,
});

const recipient = (name: string, email: string, status: "sent" | "failed" = "sent") => ({
  member_id: null,
  name,
  email,
  status,
  error: status === "failed" ? "refusé" : null,
});

const reminder = entry({ subject: "Rappel paiement", competition_ids: [7], recipients: [recipient("Léa Dupré", "lea@example.org")] });
const attestation = entry({ kind: "attestation", author: "tresorier@alj.example", template: "Attestation 2026" });
const invitation = entry({ kind: "access_invitation", author: "system", recipients: [recipient("", "nouveau@alj.example", "failed")] });
const entries = [reminder, attestation, invitation];
const names = { 7: "Coupe Rhône" };

describe("labels", () => {
  it("labels, internal kinds and failures", () => {
    expect(KIND_LABELS.competition_all_paid).toMatch(/^Interne/);
    expect(isInternal("results_batch")).toBe(true);
    expect(isInternal("competition_email")).toBe(false);
    expect(entries.map(failedCount)).toEqual([0, 0, 1]);
  });
});

describe("filterEntries", () => {
  it.each([
    ["no filter: every send", "", "", entries],
    ["by kind", "attestation", "", [attestation]],
    ["recipient name, any case and accent", "", "lea dupre", [reminder]],
    ["recipient address", "", "NOUVEAU@", [invitation]],
    ["author", "", "tresorier", [attestation]],
    ["subject", "", "paiement", [reminder]],
    ["template", "", "attestation 2026", [attestation]],
    ["competition name", "", "rhone", [reminder]],
    ["kind and search together", "competition_email", "tresorier", []],
  ] as const)("%s", (_name, kind, search, expected) => {
    expect(filterEntries(entries, { kind, search }, names)).toEqual(expected);
  });
});
