import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import type { Auth } from "../composables/auth";
import { AUTH_KEY } from "../composables/auth";
import { API_KEY, type ApiFetch } from "../lib/api";
import { CLIENT_KEY, createApiClient } from "../lib/client";
import ParametresPage from "./ParametresPage.vue";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const ANSWERS: Record<string, () => Response> = {
  "GET /api/auth/google/status": () => json({
    status: "connected", valid: true, configured: true, client_id_configured: true, refresh_token_present: true,
    user_email: "club@alj.example", backend: "firestore", db_accessible: true, error: "",
  }),
  "GET /api/cloud-db/status": () => json({
    status: "success", enabled: true, db_exists: true, db_filename: "database.db", db_size_kb: 10, member_count: 42,
    pending: 2, last_error: "", last_sync: 1_790_000_000,
  }),
  "GET /api/settings/competitions-results": () => json({
    status: "success", notification_email: "resultats@alj.example", last_run: "", last_status: "", cron_schedule: "Tous les jours à 07h00",
  }),
  "POST /api/cloud-db/sync": () => json({ status: "error", message: "Erreur de synchronisation (1 erreur(s), détails dans les journaux)." }, 500),
  "POST /api/settings/competitions-results": () => json({ status: "success", notification_email: "nouvelle@alj.example", saved: true }),
};

function render(answers = ANSWERS) {
  const calls: { method: string; path: string; body?: string }[] = [];
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url);
    const method = init?.method ?? "GET";
    calls.push({ method, path: u.pathname + u.search, body: init?.body as string | undefined });
    const answer = answers[`${method} ${u.pathname}`];
    return answer ? answer() : json({ status: "ok" });
  });
  const auth: Auth = {
    state: ref({ status: "signedIn", user: { uid: "u1", email: "admin@alj.example" }, role: "admin" }),
    login: vi.fn(), logout: vi.fn(async () => {}), retry: vi.fn(async () => {}), stop: vi.fn(),
  };
  const wrapper = mount(ParametresPage, {
    global: {
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") },
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  return { wrapper, calls, byId };
}

afterEach(() => vi.restoreAllMocks());

describe("ParametresPage", () => {
  it("shows the Google connection, the server cache and the batch settings", async () => {
    const { byId } = render();
    await flushPromises();
    expect(byId("google-status").text()).toBe("🟢 Connecté & Opérationnel");
    expect(byId("google-account").text()).toBe("club@alj.example");
    expect(byId("cache-status").text()).toBe("🟢 Cache opérationnel");
    expect(byId("cache-file").text()).toBe("database.db (10 Ko · 42 adhérents)");
    expect(byId("cache-pending").text()).toBe("⏳ 2 en attente");
    expect((byId("results-email").element as HTMLInputElement).value).toBe("resultats@alj.example");
    expect(byId("results-last-run").text()).toBe("Jamais exécuté");
  });

  it("shows a status the server could not give", async () => {
    const { byId } = render({ ...ANSWERS, "GET /api/cloud-db/status": () => json({ status: "error", message: "Erreur interne" }, 500) });
    await flushPromises();
    expect(byId("cache-status").text()).toBe("Indisponible");
    expect(byId("cache-status").element.closest("section")!.textContent).toContain("Erreur interne");
  });

  it("asks before a full rebuild, and reports a failed sync", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { byId, calls } = render();
    await flushPromises();
    await byId("cache-rebuild").trigger("click");
    expect(confirm).toHaveBeenCalledOnce();
    expect(calls.some((c) => c.method === "POST")).toBe(false);

    confirm.mockReturnValue(true);
    await byId("cache-rebuild").trigger("click");
    await flushPromises();
    expect(calls).toContainEqual(expect.objectContaining({ method: "POST", path: "/api/cloud-db/sync?force=true" }));
    expect(byId("cache-report").text()).toContain("🔴 Échec de synchronisation : Erreur de synchronisation (1 erreur(s)");
    expect(byId("toast").text()).toContain("❌ Échec de la mise à jour");
    expect(byId("cache-sync").attributes("disabled")).toBeUndefined();
  });

  it("saves the notification address, after a local check", async () => {
    const { byId, calls } = render();
    await flushPromises();
    await byId("results-email").setValue("pas-une-adresse");
    await byId("results-email").element.closest("form")!.dispatchEvent(new Event("submit"));
    expect(byId("toast").text()).toBe("❌ Veuillez saisir une adresse e-mail valide.");
    expect(calls.some((c) => c.method === "POST")).toBe(false);

    await byId("results-email").setValue("nouvelle@alj.example");
    await byId("results-email-save").element.closest("form")!.dispatchEvent(new Event("submit"));
    await flushPromises();
    const post = calls.find((c) => c.method === "POST");
    expect(post?.path).toBe("/api/settings/competitions-results");
    expect(JSON.parse(post!.body!)).toEqual({ notification_email: "nouvelle@alj.example" });
    expect(byId("toast").text()).toBe("✅ Adresse de notification enregistrée : nouvelle@alj.example");
  });
});
