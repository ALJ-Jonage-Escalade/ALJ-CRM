import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
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
  ...extra,
});
const ENTRIES = [
  entry(ME, "admin", { display_name: "Albus", last_sign_in_at: "2026-10-30T09:00:00+00:00" }),
  entry("severus@alj.example", "coach"),
];
const REQUEST = {
  email: "draco@alj.example",
  google_display_name: "Draco Malfoy",
  first_requested_at: "2026-10-29T08:00:00+00:00",
  last_requested_at: "2026-10-30T08:30:00+00:00",
};
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
  "GET /api/admin/access/requests": () => json([REQUEST]),
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
  const request = (email: string) => wrapper.find(`[data-testid="requests"] li[data-email="${email}"]`);
  return { wrapper, calls, writes, row, request };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AdministrationAccessPage", () => {
  it("lists the access entries, the requests and the history", async () => {
    const { wrapper, row, request } = render();
    await flushPromises();
    expect(row(ME).text()).toContain("Albus");
    expect(row(ME).find('[data-testid="entry-last-sign-in"]').text()).toBe("30/10/2026");
    expect(row("severus@alj.example").find('[data-testid="entry-last-sign-in"]').text()).toBe("Jamais");
    expect((row("severus@alj.example").find('[data-testid="entry-role"]').element as HTMLSelectElement).value).toBe("coach");
    expect(request("draco@alj.example").text()).toContain("Draco Malfoy");
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

  it("adds a person, after checking the address", async () => {
    const { wrapper, writes } = render({ "POST /api/admin/access/roles": (body) => json(entry("x", "coach", body as object), 201) });
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

  it("grants a request with the chosen role, or dismisses it", async () => {
    const { request, writes } = render({
      "POST /api/admin/access/requests/draco@alj.example/grant": () => json(entry("draco@alj.example", "coach"), 201),
    });
    await flushPromises();
    const grant = request("draco@alj.example").find('[data-testid="request-grant"]');
    expect(grant.attributes("disabled")).toBeDefined(); // no role chosen yet
    await request("draco@alj.example").find('[data-testid="request-role"]').setValue("coach");
    await grant.trigger("click");
    await flushPromises();
    await request("draco@alj.example").find('[data-testid="request-dismiss"]').trigger("click");
    await flushPromises();
    expect(writes()).toEqual([
      { method: "POST", path: "/api/admin/access/requests/draco@alj.example/grant", body: { role: "coach" } },
      { method: "DELETE", path: "/api/admin/access/requests/draco@alj.example", body: undefined },
    ]);
  });

  it("says when there is no request", async () => {
    const { wrapper } = render({ "GET /api/admin/access/requests": () => json([]) });
    await flushPromises();
    expect(wrapper.find('[data-testid="requests-empty"]').exists()).toBe(true);
  });

  it("shows a load error with a retry", async () => {
    const { wrapper } = render({ "GET /api/admin/access/roles": () => json({ status: "error", message: "Accès refusé" }, 403) });
    await flushPromises();
    expect(wrapper.find('[data-testid="access-load-error"]').text()).toContain("Accès refusé");
  });
});
