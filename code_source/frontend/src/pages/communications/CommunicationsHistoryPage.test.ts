import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type ApiFetch } from "../../lib/api";
import { API_KEY } from "../../lib/api";
import { CLIENT_KEY, createApiClient } from "../../lib/client";
import { json } from "../../test/harness";
import CommunicationsHistoryPage from "./CommunicationsHistoryPage.vue";

const LOG = {
  entries: [
    {
      at: "2026-11-02T09:00:00+00:00",
      author: "coach@alj.example",
      kind: "competition_email",
      template: "Relance",
      subject: "Rappel paiement",
      competition_ids: [7],
      member_ids: [3],
      recipients: [{ member_id: 3, email: "lea@example.org", name: "Léa Dupré", status: "sent", error: null }],
    },
    {
      at: "2026-11-01T09:00:00+00:00",
      author: "system",
      kind: "access_invitation",
      template: "",
      subject: "Invitation",
      competition_ids: [],
      member_ids: [],
      recipients: [{ member_id: null, email: "nouveau@alj.example", name: "", status: "failed", error: "refusé" }],
    },
  ],
  competition_names: { 7: "Coupe Rhône" },
  truncated: false,
};

function render(answers: (() => Response)[]) {
  const api: ApiFetch = vi.fn(async () => answers.shift()?.() ?? json({}, 500));
  const wrapper = mount(CommunicationsHistoryPage, {
    global: { provide: { [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") } },
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  const all = (id: string) => wrapper.findAll(`[data-testid="${id}"]`);
  return { wrapper, api, byId, all };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CommunicationsHistoryPage", () => {
  it("lists the sends with their competition, then filters them by kind and by person", async () => {
    const { byId, all } = render([() => json(LOG)]);
    await flushPromises();
    expect(all("history-entry")).toHaveLength(2);
    expect(all("history-entry")[0]!.text()).toContain("Coupe Rhône");

    await byId("history-kind").setValue("access_invitation");
    expect(all("history-entry")).toHaveLength(1);
    await byId("history-kind").setValue("");
    await byId("history-search").setValue("lea dupre");
    expect(all("history-entry")).toHaveLength(1);
    expect(all("history-entry")[0]!.text()).toContain("Rappel");
    await byId("history-search").setValue("personne");
    expect(byId("history-no-match").exists()).toBe(true);
  });

  it("says when older sends are not listed", async () => {
    const { byId } = render([() => json({ ...LOG, truncated: true })]);
    await flushPromises();
    expect(byId("history-truncated").exists()).toBe(true);
  });

  it("offline or on an error: says the history is unavailable, never « no e-mail », and retries", async () => {
    const { byId, all } = render([() => json({ detail: "Base Firestore indisponible" }, 503), () => json(LOG)]);
    await flushPromises();
    expect(byId("history-error").text()).toContain("Historique indisponible");
    expect(byId("history-empty").exists()).toBe(false);

    await byId("history-retry").trigger("click");
    await flushPromises();
    expect(byId("history-error").exists()).toBe(false);
    expect(all("history-entry")).toHaveLength(2);
  });
});
