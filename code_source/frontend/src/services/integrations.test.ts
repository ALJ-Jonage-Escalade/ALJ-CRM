import { describe, expect, it } from "vitest";
import { recordingClient } from "../test/harness";
import { createIntegrationsApi } from "./integrations";

describe("integrations service", () => {
  it("sends the server's field names and flags", async () => {
    const { client, sent } = recordingClient();
    const integrationsApi = createIntegrationsApi(client);
    await integrationsApi.googleStatus();
    await integrationsApi.googleLoginUrl("/bureau/parametres");
    await integrationsApi.testGoogle();
    await integrationsApi.updateGoogleToken("refresh-1");
    await integrationsApi.cacheStatus();
    await integrationsApi.syncCache(true);
    await integrationsApi.syncCache(false);
    await integrationsApi.syncHelloAsso();
    await integrationsApi.helloAssoCampaigns();
    await integrationsApi.chooseHelloAssoCampaign("competitions", { form_type: "Event", slug: "saison-2026" });
    expect(sent).toEqual([
      { method: "GET", path: "/api/auth/google/status", body: undefined },
      { method: "POST", path: "/api/auth/google/login", body: { return_to: "/bureau/parametres" } },
      { method: "POST", path: "/api/auth/google/test", body: undefined },
      { method: "POST", path: "/api/auth/google/update-token", body: { refresh_token: "refresh-1" } },
      { method: "GET", path: "/api/cloud-db/status", body: undefined },
      { method: "POST", path: "/api/cloud-db/sync?force=true", body: undefined },
      { method: "POST", path: "/api/cloud-db/sync?force=false", body: undefined },
      { method: "POST", path: "/api/helloasso/sync", body: undefined },
      { method: "GET", path: "/api/helloasso/campaigns", body: undefined },
      { method: "PUT", path: "/api/helloasso/campaigns/competitions", body: { form_type: "Event", slug: "saison-2026" } },
    ]);
  });
});
