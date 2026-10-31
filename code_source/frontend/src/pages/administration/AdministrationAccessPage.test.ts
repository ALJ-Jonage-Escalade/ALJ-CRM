import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { AUTH_KEY, type Auth } from "../../composables/auth";
import { dialogs } from "../../composables/dialogs";
import { API_KEY, type ApiFetch } from "../../lib/api";
import { CLIENT_KEY, createApiClient } from "../../lib/client";
import AdministrationAccessPage from "./AdministrationAccessPage.vue";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const ME = "albus@alj.example";
const entry = (email: string, role: string, extra: object = {}) => ({
  email,
  role,
  display_name: "",
  last_sign_in_at: null,
  created_at: null,
  created_by: null,
  updated_at: null,
  updated_by: null,
  invited_at: null,
  invitation_expires_at: null,
  invitation_sent_at: null,
  accepted_at: null,
  ...extra,
});
const NOW = new Date("2026-11-01T12:00:00Z");
const ENTRIES = [
  entry(ME, "admin", { display_name: "Albus", last_sign_in_at: "2026-10-30T09:00:00+00:00" }),
  entry("severus@alj.example", "coach"),
  entry("neville@alj.example", "coach", {
    invited_at: "2026-10-30T09:00:00+00:00",
    invitation_expires_at: "2026-11-06T09:00:00+00:00",
    invitation_sent_at: "2026-10-30T09:00:00+00:00",
  }),
  entry("draco@alj.example", "readonly", { invited_at: "2026-10-20T09:00:00+00:00", invitation_expires_at: "2026-10-27T09:00:00+00:00" }),
];
const invitation = (email: string, emailSent = true) => ({
  entry: entry(email, "coach", { invitation_expires_at: "2026-11-08T12:00:00+00:00" }),
  email_sent: emailSent,
  email_error: emailSent ? null : "quota dépassé",
});
const HISTORY = [
  {
    at: "2026-10-30T09:05:00+00:00",
    author: ME,
    action: "role_changed",
    target_email: "severus@alj.example",
    old_role: "readonly",
    new_role: "coach",
  },
  { at: "2026-10-01T07:00:00+00:00", author: "bootstrap", action: "bootstrap", target_email: ME, old_role: null, new_role: "admin" },
];

type Answer = (body: unknown) => Response;
const ANSWERS: Record<string, Answer> = {
  "GET /api/admin/access/roles": () => json(ENTRIES),
  "GET /api/admin/access/history": () => json(HISTORY),
};

function render(answers: Record<string, Answer> = {}) {
  const all = { ...ANSWERS, ...answers };
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    const path = decodeURIComponent(u.pathname);
    calls.push({ method, path, body });
    const answer = all[`${method} ${path}`];
    return answer ? answer(body) : json({ status: "success" });
  });
  const auth: Auth = {
    state: ref({ status: "signedIn", user: { uid: "u1", email: ME }, role: "admin" }),
    login: vi.fn(),
    logout: vi.fn(async () => {}),
    retry: vi.fn(async () => {}),
    stop: vi.fn(),
  };
  const wrapper = mount(AdministrationAccessPage, {
    global: { provide: { [AUTH_KEY]: auth, [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") } },
  });
  const writes = () => calls.filter((c) => c.method !== "GET");
  const row = (email: string) => wrapper.find(`[data-testid="access-table"] tr[data-email="${email}"]`);
  return { wrapper, calls, writes, row };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("AdministrationAccessPage", () => {
  it("lists the access entries and the history", async () => {
    const { wrapper, row } = render();
    await flushPromises();
    expect(row(ME).text()).toContain("Albus");
    expect(row(ME).find('[data-testid="entry-last-sign-in"]').text()).toBe("30/10/2026");
    expect(row("severus@alj.example").find('[data-testid="entry-last-sign-in"]').text()).toBe("Jamais");
    expect((row("severus@alj.example").find('[data-testid="entry-role"]').element as HTMLSelectElement).value).toBe("coach");
    const history = wrapper.find('[data-testid="history"]').text();
    expect(history).toContain("Rôle modifié");
    expect(history).toContain("Lecture seule → Coach");
    expect(history).toContain("Démarrage du serveur");
  });

  it("keeps the signed-in admin from removing or demoting themselves", async () => {
    const { row } = render();
    await flushPromises();
    expect(row(ME).find('[data-testid="entry-role"]').attributes("disabled")).toBeDefined();
    expect(row(ME).find('[data-testid="entry-remove"]').attributes("disabled")).toBeDefined();
    expect(row("severus@alj.example").find('[data-testid="entry-remove"]').attributes("disabled")).toBeUndefined();
  });

  it("shows where each invitation stands, with a resend for the pending and expired ones", async () => {
    const { row } = render();
    await flushPromises();
    expect(row("severus@alj.example").find('[data-testid="entry-status"]').text()).toBe("Actif");
    expect(row("severus@alj.example").find('[data-testid="entry-resend"]').exists()).toBe(false);
    expect(row("neville@alj.example").find('[data-testid="entry-status"]').text()).toBe("Invité · expire le 06/11/2026");
    expect(row("neville@alj.example").find('[data-testid="entry-email-not-sent"]').exists()).toBe(false);
    expect(row("neville@alj.example").find('[data-testid="entry-resend"]').exists()).toBe(true);
    const expired = row("draco@alj.example");
    expect(expired.find('[data-testid="entry-status"]').text()).toContain("Invitation expirée le 27/10/2026");
    expect(expired.find('[data-testid="entry-email-not-sent"]').exists()).toBe(true);
  });

  it("resends an invitation", async () => {
    const { wrapper, row, writes } = render({
      "POST /api/admin/access/roles/draco@alj.example/invitation": () => json(invitation("draco@alj.example")),
    });
    await flushPromises();
    await row("draco@alj.example").find('[data-testid="entry-resend"]').trigger("click");
    await flushPromises();
    expect(writes()).toEqual([{ method: "POST", path: "/api/admin/access/roles/draco@alj.example/invitation", body: undefined }]);
    expect(wrapper.text()).toContain("Invitation envoyée à draco@alj.example");
  });

  it("says when the invitation was kept but its e-mail failed", async () => {
    const { wrapper } = render({ "POST /api/admin/access/roles": () => json(invitation("luna@alj.example", false), 201) });
    await flushPromises();
    await wrapper.find('[data-testid="access-email"]').setValue("luna@alj.example");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("l'e-mail n'a pas pu être envoyé : quota dépassé");
  });

  it("invites a person, after checking the address", async () => {
    const { wrapper, writes } = render({ "POST /api/admin/access/roles": () => json(invitation("neville@alj.example"), 201) });
    await flushPromises();
    await wrapper.find('[data-testid="access-add"]').trigger("submit");
    expect(wrapper.find('[data-testid="access-add-error"]').text()).toContain("Saisissez");
    await wrapper.find('[data-testid="access-email"]').setValue(" neville@alj.example ");
    await wrapper.find('[data-testid="access-name"]').setValue("Neville");
    await wrapper.find('[data-testid="access-role"]').setValue("readonly");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(writes()).toEqual([
      {
        method: "POST",
        path: "/api/admin/access/roles",
        body: { email: "neville@alj.example", role: "readonly", display_name: "Neville" },
      },
    ]);
    expect((wrapper.find('[data-testid="access-email"]').element as HTMLInputElement).value).toBe("");
  });

  it("shows the server's refusal as it is", async () => {
    const { wrapper } = render({
      "POST /api/admin/access/roles": () =>
        json({ status: "error", message: "severus@alj.example a déjà un accès.", code: "already_listed" }, 409),
    });
    await flushPromises();
    await wrapper.find('[data-testid="access-email"]').setValue("severus@alj.example");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("severus@alj.example a déjà un accès.");
  });

  it("changes a role", async () => {
    const { row, writes } = render();
    await flushPromises();
    await row("severus@alj.example").find('[data-testid="entry-role"]').setValue("admin");
    await flushPromises();
    expect(writes()).toEqual([{ method: "PATCH", path: "/api/admin/access/roles/severus@alj.example", body: { role: "admin" } }]);
  });

  it("renames an entry through the prompt", async () => {
    vi.spyOn(dialogs, "prompt").mockResolvedValue("Prof. Rogue");
    const { row, writes } = render();
    await flushPromises();
    await row("severus@alj.example").find('[data-testid="entry-rename"]').trigger("click");
    await flushPromises();
    expect(writes()).toEqual([
      { method: "PATCH", path: "/api/admin/access/roles/severus@alj.example", body: { display_name: "Prof. Rogue" } },
    ]);
  });

  it("removes an access only once confirmed", async () => {
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const { row, writes } = render();
    await flushPromises();
    const remove = row("severus@alj.example").find('[data-testid="entry-remove"]');
    await remove.trigger("click");
    await flushPromises();
    expect(writes()).toEqual([]);
    await remove.trigger("click");
    await flushPromises();
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(writes()).toEqual([{ method: "DELETE", path: "/api/admin/access/roles/severus@alj.example", body: undefined }]);
  });

  it("shows a load error with a retry", async () => {
    const { wrapper } = render({ "GET /api/admin/access/roles": () => json({ status: "error", message: "Accès refusé" }, 403) });
    await flushPromises();
    expect(wrapper.find('[data-testid="access-load-error"]').text()).toContain("Accès refusé");
  });
});
