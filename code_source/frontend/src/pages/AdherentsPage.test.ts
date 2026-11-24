import { fakeAuth, json, provided } from "../test/harness";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent } from "vue";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import { type ApiFetch } from "../lib/api";
import type { Role } from "../lib/roles";
import AdherentsPage from "./AdherentsPage.vue";
import { ADHERENTS_FILTERS_STORAGE, ADHERENTS_PANEL_STORAGE, type MemberList } from "./adherents/members";
import { member } from "./adherents/members.fixture";
import { dialogs } from "../composables/dialogs";

const CRENEAUX = [
  { groupe: "Loisir adultes", tarifs: ["Adulte loisir"], categorie_age: "", type: "" },
  { groupe: "Liste d'attente", tarifs: ["Attente"], categorie_age: "", type: "" },
];
const ACTIVE: MemberList = {
  season: "2026-2027",
  creneaux: CRENEAUX,
  members: [
    member({
      user_id: 1,
      purchase_id: 11,
      last_name: "DUPONT",
      first_name: "Léa",
      tarif_name: "Adulte loisir",
      status_norm: "Validé",
      phone: "+33 6 12 34 56 78",
      email_primary: "lea@example.org",
      key: { id: 4, code: "12", given_on: "2026-09-12" },
      order_ref: "501",
      helloasso_item_id: 7,
    }),
    member({
      user_id: 2,
      purchase_id: 12,
      last_name: "MARTIN",
      first_name: "Max",
      tarif_name: "Adulte loisir",
      status_norm: "En cours",
      badge_rouge: "Oui",
    }),
    member({ user_id: 3, purchase_id: 13, last_name: "PETIT", first_name: "Zoé", tarif_name: "Attente", status_norm: "Validé" }),
  ],
};
const PAST: MemberList = {
  season: "2025-2026",
  creneaux: CRENEAUX,
  members: [member({ user_id: 4, purchase_id: 21, last_name: "ANCIEN", season_name: "2025-2026", tarif_name: "Adulte loisir" })],
};

type Answer = (req: { search: string; ifNoneMatch: string | null; body?: unknown }) => Response;
const ANSWERS: Record<string, Answer> = {
  "GET /api/seasons": () => json({ seasons: ["2026-2027", "2025-2026"], active: "2026-2027" }, 200, '"s1"'),
  "GET /api/members": ({ search, ifNoneMatch }) => {
    if (search.includes("1999")) {
      return json({ status: "error", message: "Saison inconnue", code: "not_found" }, 404);
    }
    if (search.includes("2025-2026")) {
      return json(PAST, 200, '"m-past"');
    }
    if (ifNoneMatch === '"m1"') {
      return new Response(null, { status: 304 });
    }
    return json(ACTIVE, 200, '"m1"');
  },
};

/** Opens the record's « Plus » menu: Reka UI opens it on pointerdown or the keyboard, not on a bare click. */
async function openMore(inBody: (id: string) => HTMLElement | null): Promise<void> {
  inBody("record-more")!.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await flushPromises();
}

async function render(role: Role = "admin", answers: Record<string, Answer> = ANSWERS, path = "/bureau/adherents") {
  const calls: { method: string; path: string; ifNoneMatch: string | null; body?: unknown }[] = [];
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url, "http://alj.test");
    const method = init?.method ?? "GET";
    const ifNoneMatch = new Headers(init?.headers).get("If-None-Match");
    const body = typeof init?.body === "string" && init.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, path: u.pathname + u.search, ifNoneMatch, body });
    const answer = answers[`${method} ${u.pathname}`];
    return answer ? answer({ search: u.search, ifNoneMatch, body }) : json({}, 404);
  });
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/bureau/adherents", component: AdherentsPage },
      { path: "/:any(.*)*", component: defineComponent({ render: () => null }) },
    ],
  });
  await router.push(path);
  const auth = fakeAuth({ status: "signedIn", user: { uid: "u1", email: "u@alj.example" }, role });
  const wrapper = mount(AdherentsPage, {
    attachTo: document.body,
    global: {
      plugins: [router],
      provide: provided(auth, api),
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  // Dialogs are rendered at the end of <body>
  const inBody = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const names = () => wrapper.findAll('[data-testid="data-row"]').map((tr) => tr.find("td").text());
  const writes = () => calls.filter((c) => c.method !== "GET");
  return { wrapper, calls, writes, byId, inBody, names, router };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("AdherentsPage", () => {
  it("lists the active season without the waiting list, with links to the member record", async () => {
    const { byId, names, wrapper } = await render();
    await flushPromises();
    expect(names()).toEqual(["DUPONT", "MARTIN"]);
    expect(byId("member-count").text()).toBe("2 adhérents affichés sur 3 (saison 2026-2027)");
    expect(byId("member-record").attributes("href")).toBe("/bureau/adherents?id=1&saison=2026-2027&achat=11");
    expect(wrapper.find('a[href="tel:+33612345678"]').exists()).toBe(true);
    expect((byId("season-select").element as HTMLSelectElement).value).toBe("2026-2027");
    expect(byId("season-select").text()).toContain("2026-2027 (active)");
    expect(wrapper.find("#sync-info").text()).toBe("");
    expect(byId("member-add").attributes("href")).toBe("/bureau/adherents?ajout=1");
  });

  it("polls every 20 s with the ETag: unchanged polls are 304", async () => {
    vi.useFakeTimers();
    const { calls, names } = await render();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(20_000);
    const polls = calls.filter((c) => c.path === "/api/members");
    expect(polls).toHaveLength(2);
    expect(polls[1]!.ifNoneMatch).toBe('"m1"');
    expect(names()).toEqual(["DUPONT", "MARTIN"]);
  });

  it("filters by search, status and slot, and remembers the filters but not the search", async () => {
    const { byId, names, wrapper } = await render();
    await flushPromises();
    await byId("member-search").setValue("léa");
    expect(names()).toEqual(["DUPONT"]);
    await byId("member-search").setValue("");

    await byId("status-En cours").trigger("click");
    expect(names()).toEqual(["MARTIN"]);
    await byId("status-all").trigger("click");

    await byId("filter-toggle").trigger("click");
    const groups = wrapper.findAll('[data-testid="filter-group"]');
    expect(groups.map((g) => g.text())).toEqual(["Liste d'attente1", "Loisir adultes2"]);
    expect(groups.map((g) => (g.find("input").element as HTMLInputElement).checked)).toEqual([false, true]);
    await groups[0]!.find("input").setValue(true);
    expect(names()).toEqual(["DUPONT", "MARTIN", "PETIT"]);
    await byId("filter-none").trigger("click");
    expect(wrapper.find('[data-testid="data-empty"]').text()).toBe("Aucun adhérent ne correspond aux filtres actifs.");

    await byId("member-search").setValue("dupont");
    const saved = JSON.parse(localStorage.getItem(ADHERENTS_FILTERS_STORAGE)!);
    expect(saved.groups).toEqual({ "Liste d'attente": false, "Loisir adultes": false });
    expect(saved.search).toBe("");
  });

  it("sorts by a column", async () => {
    const { byId, names } = await render();
    await flushPromises();
    await byId("sort-last_name").trigger("click");
    expect(names()).toEqual(["MARTIN", "DUPONT"]);
    await byId("sort-diplome").trigger("click"); // the red badge first
    expect(names()).toEqual(["MARTIN", "DUPONT"]);
  });

  it("switches season, and falls back to the active season when the remembered one is gone", async () => {
    const { byId, names, calls } = await render();
    await flushPromises();
    await byId("season-select").setValue("2025-2026");
    await flushPromises();
    expect(names()).toEqual(["ANCIEN"]);
    expect(byId("member-count").text()).toContain("(saison 2025-2026)");
    expect(calls.map((c) => c.path)).toContain("/api/members?season=2025-2026");

    localStorage.setItem(ADHERENTS_FILTERS_STORAGE, JSON.stringify({ season: "1999-2000" }));
    const again = await render();
    await flushPromises();
    expect(again.names()).toEqual(["DUPONT", "MARTIN"]);
  });

  it("exports the list shown to CSV, in the table's order", async () => {
    const saved: Blob[] = [];
    vi.spyOn(URL, "createObjectURL").mockImplementation((b) => {
      saved.push(b as Blob);
      return "blob:x";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { byId } = await render();
    await flushPromises();
    await byId("sort-last_name").trigger("click");
    await byId("export-csv").trigger("click");
    const text = await saved[0]!.text();
    const lines = text.replace(/^﻿/, "").split("\r\n");
    expect(lines).toHaveLength(3);
    expect(lines[1]).toMatch(/^"MARTIN";"Max"/);
    // A phone number starting with + is kept as is (lib/csv.ts)
    expect(lines[2]).toContain('"+33 6 12 34 56 78"');
  });

  it("shows a coach no admin action, but the FFME export coaches may open", async () => {
    const { byId, wrapper } = await render("coach");
    await flushPromises();
    expect(byId("member-add").exists()).toBe(false);
    expect(wrapper.find('a[href="/bureau/outils/ffme-import"]').exists()).toBe(false);
    expect(byId("export-ffme").attributes("href")).toBe("/bureau/outils/ffme");
  });

  it("opens the record of a member from the list: a coach can e-mail but not edit", async () => {
    const { byId, inBody, router } = await render("coach");
    await flushPromises();
    await byId("member-record").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({ id: "1", saison: "2026-2027", achat: "11" });
    expect(inBody("record-name")!.textContent).toBe("Léa DUPONT");
    expect(inBody("record-fields")!.textContent).toContain("lea@example.org");
    // Her key, managed in Outils › Clés
    const keyLink = inBody("record-field-link")!;
    expect(keyLink.textContent.trim()).toBe("n° 12 depuis le 12/09/2026");
    expect(keyLink.getAttribute("href")).toBe("/bureau/outils/cles?cle=4");
    expect(inBody("record-readonly")).not.toBeNull();
    expect(inBody("record-edit")).toBeNull();
    await openMore(inBody);
    expect(inBody("record-attestation")).toBeNull();
    expect(inBody("record-email")).not.toBeNull();
  });

  it("shows the first row of the list as shown in the panel, without touching the URL", async () => {
    const { byId, inBody, router, wrapper } = await render();
    await flushPromises();
    expect(inBody("record-name")!.textContent).toBe("Léa DUPONT");
    // Status badge next to the name
    expect(inBody("record-panel")!.textContent).toContain("Validé");
    expect(wrapper.findAll('[data-testid="data-row"]').map((r) => r.attributes("aria-selected"))).toEqual(["true", "false"]);
    expect(router.currentRoute.value.query).toEqual({});
    await byId("sort-last_name").trigger("click");
    expect(inBody("record-name")!.textContent).toBe("Max MARTIN");
    expect(inBody("record-panel")!.textContent).toContain("En cours");
    await byId("member-search").setValue("léa");
    expect(inBody("record-name")!.textContent).toBe("Léa DUPONT");
    await byId("member-search").setValue("personne");
    expect(inBody("record-missing")!.textContent).toBe("Aucun adhérent à afficher.");
  });

  it("selects a member on a row click, as a history entry", async () => {
    const { inBody, router, wrapper } = await render();
    await flushPromises();
    await wrapper.findAll('[data-testid="data-row"]')[1]!.find("td:nth-child(2)").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({ id: "2", saison: "2026-2027", achat: "12" });
    expect(inBody("record-name")!.textContent).toBe("Max MARTIN");
    router.back();
    await flushPromises();
    await new Promise((r) => setTimeout(r));
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({});
    expect(inBody("record-name")!.textContent).toBe("Léa DUPONT");
  });

  it("collapses the panel, remembers it, shows its columns again, and opens it on a row click", async () => {
    const { byId, inBody, wrapper } = await render();
    await flushPromises();
    expect(byId("sort-city").exists()).toBe(false);
    expect(byId("sort-email_primary").exists()).toBe(false);
    expect(byId("sort-phone").exists()).toBe(false);
    expect(byId("panel-open").exists()).toBe(false);
    await byId("side-panel-collapse").trigger("click");
    await flushPromises();
    expect(inBody("record-panel")).toBeNull();
    expect(byId("sort-city").exists()).toBe(true);
    expect(localStorage.getItem(ADHERENTS_PANEL_STORAGE)).toBe("closed");
    wrapper.unmount();

    const again = await render();
    await flushPromises();
    expect(again.inBody("record-panel")).toBeNull();
    await again.wrapper.findAll('[data-testid="data-row"]')[1]!.find("td:nth-child(2)").trigger("click");
    await flushPromises();
    expect(again.inBody("record-name")!.textContent).toBe("Max MARTIN");
    expect(again.byId("sort-city").exists()).toBe(false);
    expect(localStorage.getItem(ADHERENTS_PANEL_STORAGE)).toBe("open");
    await again.byId("side-panel-collapse").trigger("click");
    await again.byId("panel-open").trigger("click");
    expect(again.inBody("record-name")!.textContent).toBe("Max MARTIN");
    // The member already in the URL: the click does not change the route, the panel opens all the same
    await again.byId("side-panel-collapse").trigger("click");
    await again.wrapper.findAll('[data-testid="data-row"]')[1]!.find("td:nth-child(2)").trigger("click");
    await flushPromises();
    expect(again.inBody("record-name")!.textContent).toBe("Max MARTIN");
    await again.byId("side-panel-collapse").trigger("click");
    await again.wrapper.findAll('[data-testid="member-record"]')[1]!.trigger("click");
    await flushPromises();
    expect(again.inBody("record-name")!.textContent).toBe("Max MARTIN");
  });

  it("pins the first row in the URL when an action opens: a member added by a poll does not close the form", async () => {
    vi.useFakeTimers();
    let polls = 0;
    const aaron = member({ user_id: 5, purchase_id: 15, last_name: "AARON", first_name: "Abel", tarif_name: "Adulte loisir" });
    const answers: Record<string, Answer> = {
      ...ANSWERS,
      "GET /api/members": () =>
        ++polls > 1 ? json({ ...ACTIVE, members: [aaron, ...ACTIVE.members] }, 200, '"m2"') : json(ACTIVE, 200, '"m1"'),
      "GET /api/email-templates": () => json({ status: "success", templates: [], club_contact_email: "club@alj.example" }),
    };
    const { inBody, router, names } = await render("coach", answers);
    await flushPromises();
    await openMore(inBody);
    inBody("record-email")!.click();
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({ id: "1", saison: "2026-2027", achat: "11" });
    await vi.advanceTimersByTimeAsync(20_000);
    await flushPromises();
    expect(names()[0]).toBe("AARON");
    expect(inBody("record-dialog")).not.toBeNull();
    expect(inBody("record-name")!.textContent).toBe("Léa DUPONT");
  });

  it("keeps a linked member in the panel even when the filters hide it", async () => {
    const { inBody, names, wrapper } = await render("admin", ANSWERS, "/bureau/adherents?id=3&saison=2026-2027");
    await flushPromises();
    expect(names()).toEqual(["DUPONT", "MARTIN"]);
    expect(inBody("record-name")!.textContent).toBe("Zoé PETIT");
    expect(wrapper.findAll('[data-testid="data-row"]').map((r) => r.attributes("aria-selected"))).toEqual(["false", "false"]);
  });

  it("opens the record's actions in a dialog over the panel, and closes it on cancel", async () => {
    const answers: Record<string, Answer> = {
      ...ANSWERS,
      "GET /api/email-templates": () => json({ status: "success", templates: [], club_contact_email: "club@alj.example" }),
    };
    const { inBody } = await render("coach", answers);
    await flushPromises();
    expect(inBody("record-dialog")).toBeNull();
    await openMore(inBody);
    inBody("record-email")!.click();
    await flushPromises();
    expect(inBody("record-dialog")!.textContent).toContain("E-mail à l'adhérent");
    expect(inBody("record-panel")!.textContent).toContain("Léa DUPONT");
    inBody("email-cancel")!.click();
    await flushPromises();
    expect(inBody("record-dialog")).toBeNull();
  });

  it("opens a link of the former page (?id=&saison=) on its season", async () => {
    const { inBody, calls } = await render("admin", ANSWERS, "/bureau/adherents?id=4&saison=2025-2026");
    await flushPromises();
    expect(calls.map((c) => c.path)).toContain("/api/members?season=2025-2026");
    expect(inBody("record-name")!.textContent).toBe(" ANCIEN");
  });

  it("says when the member is not in the season", async () => {
    const { inBody } = await render("admin", ANSWERS, "/bureau/adherents?id=99&saison=2026-2027");
    await flushPromises();
    expect(inBody("record-missing")!.textContent).toBe("Adhérent introuvable dans la saison 2026-2027.");
  });

  it("offers to detach a HelloAsso membership to admins only", async () => {
    const shown = async (role: Role, achat: string): Promise<boolean> => {
      const { inBody, wrapper } = await render(
        role,
        ANSWERS,
        `/bureau/adherents?id=${achat === "11" ? 1 : 2}&saison=2026-2027&achat=${achat}`,
      );
      await flushPromises();
      await openMore(inBody);
      const found = inBody("record-detach") !== null;
      document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      wrapper.unmount();
      return found;
    };
    expect(await shown("admin", "11")).toBe(true);
    expect(await shown("admin", "12")).toBe(false); // entered by hand
    expect(await shown("coach", "11")).toBe(false);
  });

  it("disables the detach offline: a deletion cannot wait for the network", async () => {
    const { inBody } = await render("admin", ANSWERS, "/bureau/adherents?id=1&saison=2026-2027&achat=11");
    await flushPromises();
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    window.dispatchEvent(new Event("offline"));
    await openMore(inBody);
    expect(inBody("record-detach")!.getAttribute("data-disabled")).not.toBeNull();
    expect(inBody("record-detach")!.title).toBe("Connexion requise");
  });

  it("detaches a HelloAsso membership with a reason, then closes the record and reloads the list", async () => {
    const answers = {
      ...ANSWERS,
      "POST /api/members/purchases/11/detach-helloasso": () =>
        json({ status: "success", message: "ok", order_ref: "501", season: "2026-2027" }),
    };
    const { inBody, writes, calls, router } = await render("admin", answers, "/bureau/adherents?id=1&saison=2026-2027&achat=11");
    await flushPromises();
    await openMore(inBody);
    inBody("record-detach")!.click();
    await flushPromises();
    expect(inBody("record-dialog")!.textContent).toContain("commande 501");
    expect((inBody("detach-confirm") as HTMLButtonElement).disabled).toBe(true); // the reason is required

    const reason = inBody("detach-reason") as HTMLTextAreaElement;
    reason.value = "Inscription de Molly, pas de Léa";
    reason.dispatchEvent(new Event("input"));
    await flushPromises();
    const polled = calls.filter((c) => c.path.startsWith("/api/members?")).length;
    inBody("detach-confirm")!.click();
    await flushPromises();

    expect(writes()).toEqual([
      expect.objectContaining({ path: "/api/members/purchases/11/detach-helloasso", body: { reason: "Inscription de Molly, pas de Léa" } }),
    ]);
    expect(router.currentRoute.value.query).toEqual({ saison: "2026-2027" });
    expect(calls.filter((c) => c.path.startsWith("/api/members?")).length).toBeGreaterThan(polled);
    expect(inBody("record-dialog")).toBeNull();
    expect(document.querySelector("#toast")!.textContent).toContain("Outils › Import HelloAsso");
  });

  it("edits a record: checks the fields, sends only the changes, then reloads the list", async () => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const answers = { ...ANSWERS, "POST /api/members/update": () => json({ status: "success", message: "ok" }) };
    const { inBody, writes, calls } = await render("admin", answers, "/bureau/adherents?id=1&saison=2026-2027&achat=11");
    await flushPromises();
    inBody("record-edit")!.click();
    await flushPromises();
    const phone = inBody("member-phone") as HTMLInputElement;
    phone.value = "12";
    phone.dispatchEvent(new Event("input"));
    inBody("member-save")!.click();
    await flushPromises();
    expect(inBody("member-form")!.textContent).toContain("Numéro de téléphone invalide.");
    expect(document.activeElement).toBe(phone);
    expect(writes()).toEqual([]);

    phone.value = "06 99 88 77 66";
    phone.dispatchEvent(new Event("input"));
    (inBody("member-badge_rouge") as HTMLSelectElement).value = "Oui";
    inBody("member-badge_rouge")!.dispatchEvent(new Event("change"));
    inBody("member-save")!.click();
    await flushPromises();
    expect(writes()).toEqual([
      expect.objectContaining({
        path: "/api/members/update",
        body: { user_id: 1, purchase_id: 11, order_ref: "501", fields: { phone: "06 99 88 77 66", badge_rouge: "Oui" } },
      }),
    ]);
    expect(calls.filter((c) => c.path.startsWith("/api/members")).length).toBeGreaterThan(1); // reloaded after the write
    expect(document.querySelector("#toast")!.textContent).toContain("mise à jour avec succès");
  });

  it("adds a member to the season shown, then opens the new record", async () => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const added = member({
      user_id: 9,
      purchase_id: 90,
      last_name: "NOUVEAU",
      first_name: "Nina",
      order_ref: "MANUEL-1",
      tarif_name: "Adulte loisir",
    });
    let created = false;
    const answers: Record<string, Answer> = {
      ...ANSWERS,
      "GET /api/members": () => json(created ? { ...ACTIVE, members: [...ACTIVE.members, added] } : ACTIVE, 200, created ? '"m2"' : '"m1"'),
      "POST /api/members/create": () => {
        created = true;
        return json({
          status: "success",
          message: "Adhérent Nina NOUVEAU ajouté avec succès.",
          order_ref: "MANUEL-1",
          season: "2026-2027",
        });
      },
    };
    const { inBody, writes, router, byId } = await render("admin", answers);
    await flushPromises();
    await byId("member-add").trigger("click");
    await flushPromises();
    inBody("member-save")!.click();
    await flushPromises();
    for (const field of ["last_name", "first_name", "birth_date"]) {
      expect(inBody(`member-${field}`)!.getAttribute("aria-invalid")).toBe("true");
    }
    expect(writes()).toEqual([]);

    const type = (id: string, value: string) => {
      const input = inBody(id) as HTMLInputElement;
      input.value = value;
      input.dispatchEvent(new Event("input"));
    };
    type("member-last_name", "nouveau");
    type("member-first_name", "Nina");
    type("member-birth_date", "2012-04-05");
    inBody("member-save")!.click();
    await flushPromises();
    expect(writes()[0]!.body).toEqual(
      expect.objectContaining({
        season: "2026-2027",
        fields: expect.objectContaining({
          last_name: "NOUVEAU",
          first_name: "Nina",
          birth_date: "2012-04-05",
          tarif_name: "Adulte loisir",
          amount: 0,
        }),
      }),
    );
    expect(router.currentRoute.value.query).toEqual({ id: "9", saison: "2026-2027", achat: "90" });
  });

  it("offers the member templates only, the default one chosen, with labels, and sends keys", async () => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const template = (name: string, kind: string, is_default = false) => ({
      name,
      kind,
      is_default,
      subject: "Rappel {first_name}",
      body: "Bonjour {first_name}, {amount} €",
      sender_email: "",
      sender_name: "",
    });
    const answers: Record<string, Answer> = {
      ...ANSWERS,
      "GET /api/email-templates": () =>
        json({
          status: "success",
          templates: [template("Bienvenue", "adherent"), template("Relance", "adherent", true), template("Coupe", "competition", true)],
          club_contact_email: "club@alj.example",
        }),
      "POST /api/send-email": () => json({ status: "success", sent_count: 1 }),
    };
    const { inBody, writes } = await render("admin", answers, "/bureau/adherents?id=1&saison=2026-2027");
    await flushPromises();
    await openMore(inBody);
    inBody("record-email")!.click();
    await flushPromises();
    const select = inBody("email-template") as HTMLSelectElement;
    expect([...select.options].map((option) => option.textContent.trim())).toEqual([
      "-- E-mail libre / personnalisé --",
      "Bienvenue",
      "Relance",
    ]);
    expect(select.value).toBe("Relance");
    expect((inBody("email-subject") as HTMLInputElement).value).toBe("Rappel {Prénom}");
    expect((inBody("email-body") as HTMLTextAreaElement).value).toBe("Bonjour {Prénom}, {Montant de l'adhésion} €");
    const offered = [...inBody("email-body-variables")!.querySelectorAll("button")].map((b) => b.textContent.trim());
    expect(offered).toContain("{Montant de l'adhésion}");
    expect(offered).not.toContain("{Nom de la compétition}");
    inBody("email-send")!.click();
    await flushPromises();
    expect(writes()[0]!.body).toEqual(
      expect.objectContaining({ subject: "Rappel {first_name}", body: "Bonjour {first_name}, {amount} €" }),
    );
  });

  it.each<Role>(["admin", "coach"])("sends an e-mail from the record (%s)", async (role) => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const answers: Record<string, Answer> = {
      ...ANSWERS,
      "GET /api/email-templates": () =>
        json({
          status: "success",
          templates: [
            {
              name: "Rappel",
              subject: "Rappel {first_name}",
              body: 'Bonjour {first_name}, <b>voir</b> <a href="https://alj.example/fiche">la fiche</a>',
              sender_email: "",
              sender_name: "",
              kind: "adherent",
            },
          ],
          club_contact_email: "club@alj.example",
        }),
      "POST /api/send-email": () => json({ status: "success", sent_count: 1 }),
    };
    const { inBody, writes } = await render(role, answers, "/bureau/adherents?id=1&saison=2026-2027");
    await flushPromises();
    await openMore(inBody);
    inBody("record-email")!.click();
    await flushPromises();
    inBody("email-send")!.click();
    await flushPromises();
    expect(inBody("email-problem")!.textContent).toContain("renseigner le sujet et le message");

    const select = inBody("email-template") as HTMLSelectElement;
    select.value = "Rappel";
    select.dispatchEvent(new Event("change"));
    await flushPromises();
    expect(inBody("email-preview")!.textContent).toContain("Sujet : Rappel Léa");
    expect(inBody("email-preview")!.textContent).toContain("club@alj.example");
    const link = inBody("email-preview")!.querySelector("a");
    expect([link?.getAttribute("href"), link?.textContent]).toEqual(["https://alj.example/fiche", "la fiche"]);
    expect(inBody("email-preview")!.querySelector("b")?.textContent).toBe("voir");
    inBody("email-send")!.click();
    await flushPromises();
    expect(writes()[0]).toEqual(expect.objectContaining({ path: "/api/send-email" }));
    expect(writes()[0]!.body).toEqual(
      expect.objectContaining({
        subject: "Rappel {first_name}",
        recipients: [expect.objectContaining({ email: "lea@example.org", tarif: "Adulte loisir", amount: null })],
      }),
    );
    expect(document.querySelector("#toast")!.textContent).toContain("E-mail envoyé avec succès");
    expect(inBody("record-dialog")).toBeNull(); // back to the record in the panel
    expect(inBody("record-name")).not.toBeNull();
  });

  it("previews and sends the payment certificate of the membership", async () => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:pdf");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const paid = {
      ...ACTIVE,
      members: [{ ...ACTIVE.members[0]!, amount: 180, payer_email: "parent@example.org" }, ...ACTIVE.members.slice(1)],
    };
    const answers: Record<string, Answer> = {
      ...ANSWERS,
      "GET /api/members": () => json(paid, 200, '"paid"'),
      "GET /api/email-templates": () => json({ status: "success", templates: [], club_contact_email: "club@alj.example" }),
      "POST /api/attestations/preview": () =>
        new Response(new Blob(["%PDF"]), { status: 200, headers: { "Content-Type": "application/pdf" } }),
      "POST /api/attestations/send": () => json({ status: "success", message: "ok", email_sent_date: "22/10/2026", filename: "a.pdf" }),
    };
    const { inBody, writes } = await render("admin", answers, "/bureau/adherents?id=1&saison=2026-2027");
    await flushPromises();
    await openMore(inBody);
    inBody("record-attestation")!.click();
    await flushPromises();
    expect(inBody("attestation-pdf")!.getAttribute("src")).toBe("blob:pdf");
    expect((inBody("attestation-to") as HTMLInputElement).value).toBe("parent@example.org");
    expect((inBody("attestation-subject") as HTMLInputElement).value).toContain("Attestation de paiement");
    expect((inBody("attestation-body") as HTMLTextAreaElement).value).toContain("Bonjour {Prénom},");
    inBody("attestation-send")!.click();
    await flushPromises();
    expect(writes().map((w) => w.path)).toEqual(["/api/attestations/preview", "/api/attestations/send"]);
    expect(writes()[0]!.body).toEqual({ purchase_id: 11, season: "2026-2027" });
    expect(writes()[1]!.body).toEqual(
      expect.objectContaining({
        purchase_id: 11,
        to_email: "parent@example.org",
        template_name: "Attestation échéance",
        body: expect.stringContaining("Bonjour {first_name},") as unknown,
      }),
    );
    expect(document.querySelector("#toast")!.textContent).toContain("Attestation envoyée avec succès");
  });

  it("refuses a certificate for a membership without amount", async () => {
    const answers: Record<string, Answer> = {
      ...ANSWERS,
      "GET /api/email-templates": () => json({ status: "success", templates: [], club_contact_email: "club@alj.example" }),
    };
    const { inBody, writes } = await render("admin", answers, "/bureau/adherents?id=1&saison=2026-2027");
    await flushPromises();
    await openMore(inBody);
    inBody("record-attestation")!.click();
    await flushPromises();
    expect(inBody("attestation-ineligible")!.textContent).toContain("le montant est nul");
    expect(inBody("attestation-send")!.hasAttribute("disabled")).toBe(true);
    expect(writes()).toEqual([]);
  });

  it("does not open the add form for a coach", async () => {
    const { inBody } = await render("coach", ANSWERS, "/bureau/adherents?ajout=1");
    await flushPromises();
    expect(inBody("add-dialog")).toBeNull();
  });
});
