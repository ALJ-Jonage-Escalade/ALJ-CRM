/* Outils › Clés (plans/club-keys.md), through the app's routes: the page talks to a fake API. */
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { AUTH_KEY, type Auth } from "../../composables/auth";
import { dialogs } from "../../composables/dialogs";
import { API_KEY, type ApiFetch } from "../../lib/api";
import { CLIENT_KEY, createApiClient } from "../../lib/client";
import type { Role } from "../../lib/roles";
import { routes } from "../../router";
import type { Key } from "./keys";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Answer = (body: unknown) => Response;

async function render(role: Role, keys: Key[], extra: Record<string, Answer> = {}, path = "/bureau/outils/cles") {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const answers: Record<string, Answer> = {
    "GET /api/seasons": () => json({ seasons: ["2026-2027"], active: "2026-2027" }),
    "GET /api/keys": () => json(keys),
    ...extra,
  };
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url, "http://alj.test");
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path: u.pathname, body });
    const answer = answers[`${method} ${u.pathname}`];
    return answer ? answer(body) : json({}, 404);
  });
  const auth: Auth = {
    state: ref({ status: "signedIn", user: { uid: "u1", email: "u@alj.example" }, role }),
    login: vi.fn(),
    logout: vi.fn(async () => {}),
    retry: vi.fn(async () => {}),
    stop: vi.fn(),
  };
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push(path);
  mount(RouterView, {
    attachTo: document.body,
    global: {
      plugins: [router],
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") },
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  await flushPromises();
  const byId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const all = (id: string) => [...document.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`)];
  const sent = (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path);
  return { byId, all, sent };
}

const HARRY = {
  user_id: 7,
  last_name: "POTTER",
  first_name: "Harry",
  given_on: "2026-09-12",
  comment: "Remise au forum",
  member_this_season: true,
  season: "2026-2027",
};
const KEYS: Key[] = [
  { id: 1, code: "10", status: "assigned", holder: HARRY, archive: null },
  { id: 2, code: "2", status: "available", holder: null, archive: null },
  { id: 3, code: "B1", status: "available", holder: null, archive: null },
];
const MEMBERS = {
  season: "2026-2027",
  creneaux: [],
  members: [
    { user_id: 7, last_name: "POTTER", first_name: "Harry" },
    { user_id: 8, last_name: "WEASLEY", first_name: "Ron" },
    { user_id: 8, last_name: "WEASLEY", first_name: "Ron" }, // two memberships, one person
    { user_id: 9, last_name: "GRANGER", first_name: "Hermione" },
  ],
};
const typeIn = async (el: HTMLElement | null, value: string) => {
  (el as HTMLInputElement).value = value;
  el!.dispatchEvent(new Event("input"));
  await flushPromises();
};

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("OutilsKeysPage", () => {
  it("lists the keys in natural order with their counts, read only for a coach", async () => {
    const { byId, all } = await render("coach", KEYS);
    expect(all("key-code").map((c) => c.textContent.trim())).toEqual(["2", "10", "B1"]);
    expect(byId("key-counts")!.textContent.trim()).toBe("1 attribuée · 2 disponibles · 0 archivée");
    expect(byId("key-add")).toBeNull();
  });

  it("filters the keys on the search", async () => {
    const { byId, all } = await render("coach", KEYS);
    const search = byId("key-search") as HTMLInputElement;
    search.value = "b";
    search.dispatchEvent(new Event("input"));
    await flushPromises();
    expect(all("key-code").map((c) => c.textContent.trim())).toEqual(["B1"]);
  });

  it("lets an admin add a key, then reloads the list", async () => {
    const keys = [...KEYS];
    const { byId, all, sent } = await render("admin", keys, {
      "POST /api/keys": (body) => {
        const added: Key = { id: 4, code: (body as { code: string }).code, status: "available", holder: null, archive: null };
        keys.push(added);
        return json(added, 201);
      },
    });
    vi.spyOn(dialogs, "prompt").mockResolvedValue("7");
    byId("key-add")!.click();
    await flushPromises();
    expect(sent("POST", "/api/keys").map((c) => c.body)).toEqual([{ code: "7" }]);
    expect(all("key-code").map((c) => c.textContent.trim())).toEqual(["2", "7", "10", "B1"]);
    expect(byId("toast")!.textContent).toBe("✅ Clé « 7 » ajoutée.");
  });

  it("shows why a key could not be added", async () => {
    const { byId } = await render("admin", KEYS, {
      "POST /api/keys": () => json({ status: "error", message: "La clé « 2 » existe déjà.", code: "duplicate_code" }, 409),
    });
    vi.spyOn(dialogs, "prompt").mockResolvedValue("2");
    byId("key-add")!.click();
    await flushPromises();
    expect(byId("toast")!.textContent).toBe("❌ La clé « 2 » existe déjà.");
  });

  it("shows who holds a key, links to their record and flags those who did not renew", async () => {
    const gone = { ...HARRY, user_id: 9, last_name: "DIGGORY", first_name: "Cedric", member_this_season: false, season: "2025-2026" };
    const keys: Key[] = [...KEYS, { id: 4, code: "11", status: "assigned", holder: gone, archive: null }];
    const { byId, all } = await render("coach", keys);
    const holders = all("key-holder");
    expect(holders.map((h) => h.textContent.trim())).toEqual(["POTTER Harry", "DIGGORY Cedric ⚠️"]);
    expect(holders[0]!.querySelector("a")!.getAttribute("href")).toBe("/bureau/adherents?id=7&saison=2026-2027");
    expect(holders[1]!.querySelector("a")!.getAttribute("href")).toBe("/bureau/adherents?id=9&saison=2025-2026");
    expect(all("key-given-on").map((d) => d.textContent.trim())).toEqual(["12/09/2026", "12/09/2026"]);
    expect(byId("key-actions")).toBeNull(); // nothing to do for a coach

    (byId("key-only-flagged") as HTMLInputElement).click();
    await flushPromises();
    expect(all("key-code").map((c) => c.textContent.trim())).toEqual(["11"]);
  });

  it("lets an admin hand a key to a member of the season who holds none", async () => {
    const { byId, all, sent } = await render("admin", KEYS, {
      "GET /api/members": () => json(MEMBERS),
      "POST /api/keys/2/assignments": () => json({ status: "success" }),
    });
    byId("key-assign-2")!.click();
    await flushPromises();
    expect(all("assign-member").map((m) => m.textContent.trim())).toEqual([
      "GRANGER Hermione",
      "POTTER Harry — détient déjà la clé 10",
      "WEASLEY Ron",
    ]);
    expect(all("assign-member")[1]!.hasAttribute("disabled")).toBe(true);
    await typeIn(byId("assign-search"), "wea");
    expect(all("assign-member").map((m) => m.textContent.trim())).toEqual(["WEASLEY Ron"]);
    all("assign-member")[0]!.click();
    await flushPromises();
    expect((byId("assign-search") as HTMLInputElement).value).toBe("WEASLEY Ron");
    expect(all("assign-member")).toEqual([]);
    await typeIn(byId("assign-search"), "WEASLEY");
    expect(all("assign-member").map((m) => m.textContent.trim())).toEqual(["WEASLEY Ron"]);
    expect(byId("assign-submit")!.hasAttribute("disabled")).toBe(true);
    all("assign-member")[0]!.click();
    await flushPromises();
    await typeIn(byId("assign-date"), "2026-10-01");
    await typeIn(byId("assign-comment"), "Caution");
    byId("assign-submit")!.click();
    await flushPromises();
    expect(sent("POST", "/api/keys/2/assignments").map((c) => c.body)).toEqual([
      { user_id: 8, given_on: "2026-10-01", comment: "Caution" },
    ]);
    expect(byId("toast")!.textContent).toBe("✅ Clé « 2 » remise à WEASLEY Ron.");
    expect(sent("GET", "/api/keys")).toHaveLength(2);
  });

  it("lets an admin record the return of a key", async () => {
    const { byId, sent } = await render("admin", KEYS, { "POST /api/keys/1/return": () => json({ status: "success" }) });
    byId("key-return-1")!.click();
    await flushPromises();
    expect((byId("return-date") as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}$/); // today
    await typeIn(byId("return-date"), "2027-06-30");
    await typeIn(byId("return-comment"), "Fin de saison");
    byId("return-submit")!.click();
    await flushPromises();
    expect(sent("POST", "/api/keys/1/return").map((c) => c.body)).toEqual([{ returned_on: "2027-06-30", comment: "Fin de saison" }]);
    expect(byId("toast")!.textContent).toBe("✅ Retour de la clé « 10 » enregistré.");
  });

  describe("history panel", () => {
    const HISTORY = [
      {
        kind: "assignment",
        id: 31,
        user_id: 9,
        last_name: "DIGGORY",
        first_name: "Cedric",
        given_on: "2025-09-10",
        returned_on: "2026-06-30",
        comment: "Forum",
        return_comment: "Fin de saison",
        by: "albus@alj.example",
      },
      { kind: "event", id: 5, type: "renamed", date: "2026-07-01", comment: "9 → 10", by: "albus@alj.example" },
      {
        kind: "assignment",
        id: 32,
        user_id: 7,
        last_name: "POTTER",
        first_name: "Harry",
        given_on: "2026-09-12",
        returned_on: null,
        comment: "Remise au forum",
        return_comment: "",
        by: "minerva@alj.example",
      },
    ];
    const openRow = async (byId: (id: string) => HTMLElement | null) => {
      document.querySelector<HTMLElement>('[data-testid="data-row"][data-id="1"] td')!.click();
      await flushPromises();
      expect(byId("key-panel")).not.toBeNull();
    };

    it("shows the key's history, oldest first, read only for a coach", async () => {
      const { byId, all } = await render("coach", KEYS, { "GET /api/keys/1/history": () => json(HISTORY) });
      await openRow(byId);
      // textContent joins the entry's lines without a space
      expect(all("history-entry").map((e) => e.textContent.replace(/\s+/g, " ").trim())).toEqual([
        "👤 DIGGORY Cedricdu 10/09/2025 au 30/06/2026Remise : ForumRetour : Fin de saisonpar albus@alj.example",
        "✏️ Code modifié le 01/07/2026 9 → 10par albus@alj.example",
        "👤 POTTER Harrydepuis le 12/09/2026Remise : Remise au forumpar minerva@alj.example",
      ]);
      expect(byId("key-rename")).toBeNull();
      expect(byId("assignment-edit-32")).toBeNull();
    });

    it("lets an admin rename the key", async () => {
      const { byId, sent } = await render("admin", KEYS, {
        "GET /api/keys/1/history": () => json(HISTORY),
        "PATCH /api/keys/1": () => json({ status: "success" }),
      });
      await openRow(byId);
      vi.spyOn(dialogs, "prompt").mockResolvedValue("10-B");
      byId("key-rename")!.click();
      await flushPromises();
      expect(sent("PATCH", "/api/keys/1").map((c) => c.body)).toEqual([{ code: "10-B" }]);
      expect(byId("toast")!.textContent).toBe("✅ Clé « 10 » renommée en « 10-B ».");
      expect(sent("GET", "/api/keys/1/history")).toHaveLength(2);
    });

    it("lets an admin correct an assignment", async () => {
      const { byId, sent } = await render("admin", KEYS, {
        "GET /api/keys/1/history": () => json(HISTORY),
        "PATCH /api/key-assignments/31": () => json({ status: "success" }),
      });
      await openRow(byId);
      byId("assignment-edit-31")!.click();
      await flushPromises();
      expect((byId("edit-given-on") as HTMLInputElement).value).toBe("2025-09-10");
      await typeIn(byId("edit-returned-on"), "2026-07-01");
      byId("edit-submit")!.click();
      await flushPromises();
      expect(sent("PATCH", "/api/key-assignments/31").map((c) => c.body)).toEqual([
        { given_on: "2025-09-10", returned_on: "2026-07-01", comment: "Forum", return_comment: "Fin de saison" },
      ]);
      expect(byId("toast")!.textContent).toBe("✅ Attribution corrigée.");
    });

    it("lets an admin delete the latest assignment only, after confirming", async () => {
      const { byId, sent } = await render("admin", KEYS, {
        "GET /api/keys/1/history": () => json(HISTORY),
        "DELETE /api/key-assignments/32": () => json({ status: "success" }),
      });
      await openRow(byId);
      expect(byId("assignment-delete-31")).toBeNull();
      const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
      byId("assignment-delete-32")!.click();
      await flushPromises();
      expect(confirm.mock.calls[0]![0].variant).toBe("danger");
      expect(sent("DELETE", "/api/key-assignments/32")).toHaveLength(1);
      expect(byId("toast")!.textContent).toBe("✅ Attribution supprimée.");
    });
  });

  describe("archives", () => {
    const LOST: Key = { id: 5, code: "7", status: "archived", holder: null, archive: { date: "2026-11-03", comment: "Perdue" } };

    it("hides the archived keys behind a toggle, as the competitions do", async () => {
      const { byId, all } = await render("coach", [...KEYS, LOST]);
      expect(all("key-code").map((c) => c.textContent.trim())).toEqual(["2", "10", "B1"]);
      expect(byId("archived-keys")).toBeNull();
      const toggle = byId("toggle-key-archives")!;
      expect(toggle.textContent.trim()).toBe("🗂 Afficher les archives (1)");
      toggle.click();
      await flushPromises();
      expect(toggle.textContent.trim()).toBe("🙈 Masquer les archives");
      expect(all("archived-key").map((k) => k.textContent.replace(/\s+/g, " ").trim())).toEqual([
        "🔑 7 · 📦 Archivée le 03/11/2026 · Perdue",
      ]);
    });

    it("has no archives toggle without an archived key", async () => {
      const { byId } = await render("coach", KEYS);
      expect(byId("toggle-key-archives")).toBeNull();
    });

    it("lets an admin archive a key from its panel, with a reason", async () => {
      const { byId, sent } = await render("admin", KEYS, {
        "GET /api/keys/1/history": () => json([]),
        "POST /api/keys/1/archive": () => json({ status: "success" }),
      });
      document.querySelector<HTMLElement>('[data-testid="data-row"][data-id="1"] td')!.click();
      await flushPromises();
      byId("panel-archive")!.click();
      await flushPromises();
      expect(byId("archive-dialog")!.textContent).toContain("POTTER Harry ne la détiendra plus");
      expect(byId("archive-submit")!.hasAttribute("disabled")).toBe(true); // a reason is required
      await typeIn(byId("archive-date"), "2026-11-03");
      await typeIn(byId("archive-comment"), "Perdue");
      byId("archive-submit")!.click();
      await flushPromises();
      expect(sent("POST", "/api/keys/1/archive").map((c) => c.body)).toEqual([{ archived_on: "2026-11-03", comment: "Perdue" }]);
      expect(byId("toast")!.textContent).toBe("✅ Clé « 10 » archivée.");
    });

    it("lets an admin restore an archived key", async () => {
      const { byId, all, sent } = await render("admin", [...KEYS, LOST], {
        "GET /api/keys/5/history": () => json([]),
        "POST /api/keys/5/restore": () => json({ status: "success" }),
      });
      byId("toggle-key-archives")!.click();
      await flushPromises();
      all("archived-key")[0]!.click();
      await flushPromises();
      expect(byId("panel-archive")).toBeNull();
      vi.spyOn(dialogs, "prompt").mockResolvedValue("Retrouvée");
      byId("panel-restore")!.click();
      await flushPromises();
      expect(sent("POST", "/api/keys/5/restore").map((c) => c.body)).toEqual([{ comment: "Retrouvée" }]);
      expect(byId("toast")!.textContent).toBe("✅ Clé « 7 » restaurée : elle est de nouveau disponible.");
    });
  });

  it("opens the key a member record links to", async () => {
    const { byId } = await render("coach", KEYS, { "GET /api/keys/1/history": () => json([]) }, "/bureau/outils/cles?cle=1");
    expect(byId("key-panel")!.getAttribute("aria-label")).toBe("🔑 Clé 10");
  });
});
