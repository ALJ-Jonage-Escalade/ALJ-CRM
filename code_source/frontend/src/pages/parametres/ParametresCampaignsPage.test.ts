import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { dialogs } from "../../composables/dialogs";
import { API_KEY, type ApiFetch } from "../../lib/api";
import { CLIENT_KEY, createApiClient, type Schemas } from "../../lib/client";
import ParametresCampaignsPage from "./ParametresCampaignsPage.vue";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const campaign = (slug: string, extra: Partial<Schemas["HelloAssoCampaign"]> = {}): Schemas["HelloAssoCampaign"] => ({
  form_type: "Event",
  slug,
  title: slug,
  private_title: "",
  state: "Public",
  activity_type: "Compétition",
  url: `https://www.helloasso.com/associations/club/evenements/${slug}`,
  start_date: null,
  end_date: null,
  created_at: null,
  active: false,
  warning: null,
  ...extra,
});

function campaignsBody(competitionsActive: string | null = "competitions-2025"): Schemas["HelloAssoCampaigns"] {
  return {
    error: null,
    warning: null,
    others: [campaign("soiree-club", { title: "Soirée du club", activity_type: "Fête", start_date: "2026-12-12T19:00:00+01:00" })],
    membership: {
      active: { form_type: "Membership", slug: "adhesion-2026" },
      configured: false,
      campaigns: [
        campaign("adhesion-2026", {
          form_type: "Membership",
          title: "Adhésion 2026-2027",
          private_title: "Interne",
          created_at: "2026-07-01T10:00:00+02:00",
          active: true,
        }),
      ],
    },
    competitions: {
      active: competitionsActive ? { form_type: "Event", slug: competitionsActive } : null,
      configured: competitionsActive !== null,
      campaigns: [
        campaign("competitions-2027", { title: "Compétitions 2027-2028", state: "Draft" }),
        campaign("competitions-2026", {
          title: "Compétitions 2026-2027",
          state: "Private",
          start_date: "2026-09-15T00:00:00+02:00",
          end_date: "2027-06-30T23:59:00+02:00",
          active: competitionsActive === "competitions-2026",
        }),
        campaign("competitions-2025", {
          title: "Compétitions 2025-2026",
          state: "Disabled",
          active: competitionsActive === "competitions-2025",
          warning: "Campagne désactivée sur HelloAsso",
        }),
      ],
    },
  };
}

function render(answers: Record<string, (body?: string) => Response>) {
  const calls: { method: string; path: string; body?: string }[] = [];
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url);
    const method = init?.method ?? "GET";
    const body = init?.body as string | undefined;
    calls.push({ method, path: u.pathname, body });
    const answer = answers[`${method} ${u.pathname}`];
    return answer ? answer(body) : json({ status: "error", message: "inattendu" }, 500);
  });
  const wrapper = mount(ParametresCampaignsPage, {
    global: {
      provide: { [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") },
      stubs: { RouterLink: { template: "<a><slot /></a>" } },
    },
  });
  const section = (kind: string) => wrapper.find(`[data-testid="campaigns-${kind}"]`);
  const row = (kind: string, slug: string) => section(kind).find(`[data-slug="${slug}"]`);
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  return { wrapper, calls, section, row, byId };
}

afterEach(() => vi.restoreAllMocks());

describe("ParametresCampaignsPage", () => {
  it("shows both tables with dates, states and the active campaigns", async () => {
    const { section, row } = render({ "GET /api/helloasso/campaigns": () => json(campaignsBody()) });
    await flushPromises();

    const membership = row("membership", "adhesion-2026");
    expect(membership.text()).toContain("Interne");
    expect(membership.find('[data-testid="campaign-start"]').text()).toBe("—");
    expect(membership.find('[data-testid="campaign-created"]').text()).toBe("01/07/2026");
    expect(membership.find('[data-testid="campaign-active"]').exists()).toBe(true);
    expect(section("membership").find('[data-testid="campaigns-default"]').exists()).toBe(true);

    const current = row("competitions", "competitions-2026");
    expect(current.find('[data-testid="campaign-state"]').text()).toBe("Privé");
    expect(current.find('[data-testid="campaign-start"]').text()).toBe("15/09/2026");
    expect(current.find('[data-testid="campaign-end"]').text()).toBe("30/06/2027");
    expect(current.find("a").attributes("href")).toBe("https://www.helloasso.com/associations/club/evenements/competitions-2026");

    const draft = row("competitions", "competitions-2027");
    expect(draft.find('[data-testid="campaign-state"]').text()).toBe("Brouillon");
    expect(draft.find('[data-testid="campaign-choose"]').exists()).toBe(true);

    const old = row("competitions", "competitions-2025");
    expect(old.find('[data-testid="campaign-state"]').text()).toBe("Désactivé");
    expect(old.find('[data-testid="campaign-warning"]').text()).toContain("Campagne désactivée sur HelloAsso");
    expect(section("competitions").find('[data-testid="campaigns-active"]').text()).toContain("Compétitions 2025-2026");
    expect(section("competitions").find('[data-testid="campaigns-default"]').exists()).toBe(false);

    const party = row("others", "soiree-club");
    expect(party.find('[data-testid="campaign-activity"]').text()).toBe("Fête");
    expect(party.find('[data-testid="campaign-start"]').text()).toBe("12/12/2026");
    expect(party.find('[data-testid="campaign-choose"]').exists()).toBe(false);
    expect(row("competitions", "soiree-club").exists()).toBe(false);
  });

  it("chooses a campaign once confirmed, then shows it active and the sync notice", async () => {
    let active = "competitions-2025";
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const { calls, row, byId } = render({
      "GET /api/helloasso/campaigns": () => json(campaignsBody(active)),
      "PUT /api/helloasso/campaigns/competitions": (body) => {
        active = (JSON.parse(body ?? "{}") as { slug: string }).slug;
        return json({ form_type: "Event", slug: active });
      },
    });
    await flushPromises();
    await row("competitions", "competitions-2026").find('[data-testid="campaign-choose"]').trigger("click");
    await flushPromises();

    expect(confirm.mock.calls[0]![0].message).toContain("Actuelle : « Compétitions 2025-2026 »\nNouvelle : « Compétitions 2026-2027 »");
    const put = calls.find((c) => c.method === "PUT");
    expect(JSON.parse(put!.body!)).toEqual({ form_type: "Event", slug: "competitions-2026" });
    expect(row("competitions", "competitions-2026").find('[data-testid="campaign-active"]').exists()).toBe(true);
    expect(row("competitions", "competitions-2025").find('[data-testid="campaign-choose"]').exists()).toBe(true);
    expect(byId("campaigns-sync-notice").text()).toContain("Compétitions › HelloAsso");
    expect(byId("toast").text()).toContain("Campagne active : Compétitions 2026-2027");
  });

  it("changes nothing when the confirmation is cancelled", async () => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(false);
    const { calls, row, byId } = render({ "GET /api/helloasso/campaigns": () => json(campaignsBody(null)) });
    await flushPromises();
    expect(byId("campaigns-none").exists()).toBe(true);
    await row("competitions", "competitions-2026").find('[data-testid="campaign-choose"]').trigger("click");
    await flushPromises();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    expect(byId("campaigns-sync-notice").exists()).toBe(false);
  });

  it("keeps the active campaigns and offers a retry when HelloAsso can't be read", async () => {
    let failing = true;
    const unreachable = (): Response => {
      const body = campaignsBody();
      return json({
        ...body,
        error: "Impossible de lire les campagnes sur HelloAsso pour le moment.",
        membership: { ...body.membership, campaigns: [] },
        competitions: { ...body.competitions, campaigns: [] },
        others: [],
      });
    };
    const { section, byId, wrapper } = render({
      "GET /api/helloasso/campaigns": () => (failing ? unreachable() : json(campaignsBody())),
    });
    await flushPromises();
    expect(byId("campaigns-helloasso-error").text()).toContain("Impossible de lire les campagnes sur HelloAsso");
    expect(section("competitions").find('[data-testid="campaigns-active"]').text()).toContain("competitions-2025");
    expect(wrapper.find('[data-testid="campaign-choose"]').exists()).toBe(false);
    expect(section("others").exists()).toBe(false);

    failing = false;
    await byId("campaigns-retry").trigger("click");
    await flushPromises();
    expect(byId("campaigns-helloasso-error").exists()).toBe(false);
    expect(wrapper.findAll('[data-testid="campaign-choose"]').length).toBeGreaterThan(0);
  });

  it("warns when the activity of some forms could not be read", async () => {
    const warning = "Activité de 1 formulaire(s) illisible sur HelloAsso pour le moment : classé(s) dans « Autres ».";
    const { byId } = render({ "GET /api/helloasso/campaigns": () => json({ ...campaignsBody(), warning }) });
    await flushPromises();
    expect(byId("campaigns-helloasso-warning").text()).toContain(warning);
    expect(byId("campaigns-helloasso-error").exists()).toBe(false);
  });

  it("reports a request that failed", async () => {
    const { byId } = render({
      "GET /api/helloasso/campaigns": () => json({ status: "error", message: "Réglages indisponibles" }, 503),
    });
    await flushPromises();
    expect(byId("campaigns-load-error").text()).toContain("Réglages indisponibles");
  });
});
