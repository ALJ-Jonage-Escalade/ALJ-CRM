import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import type { ApiFetch } from "../../lib/api";
import { fakeAuth, json, provided } from "../../test/harness";
import { OUTILS_KEY } from "./context";
import type { MemberStatsRecord } from "./stats/memberStats";
import OutilsStatsPage from "./OutilsStatsPage.vue";

const record = (userId: number, change: Partial<MemberStatsRecord> = {}): MemberStatsRecord => ({
  user_id: userId,
  sex: "F",
  age: 30,
  age_band: "30 à 39 ans",
  city: "Jonage",
  group: "Adulte",
  status: "Validé",
  season: "2026-2027",
  returning: true,
  order_month: "2026-06",
  ...change,
});

const COMPETITIONS = [
  {
    id: 1,
    nom: "Coupe",
    date_competition: "2026-10-04",
    prix: 12.5,
    participants: [
      { adherent_id: 1, nom: "N", prenom: "P", selectionne: true, classement: "1" },
      { adherent_id: 2, nom: "N", prenom: "P", selectionne: true, classement: "3" },
    ],
  },
  {
    id: 2,
    nom: "Open",
    date_competition: "2025-11-20",
    participants: [{ adherent_id: 1, nom: "N", prenom: "P", selectionne: true, classement: "2" }],
  },
];

const RECORDS = [record(1), record(2, { sex: "H" }), record(3, { sex: "H" }), record(4, { sex: "F", season: "2025-2026" })];

async function render(answer: () => Promise<Response> | Response = () => json({ records: RECORDS })) {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null); // jsdom draws no canvas: the figures tables are read
  const calls: string[] = [];
  const api: ApiFetch = vi.fn(async (url: string) => {
    const path = new URL(url, "http://alj.test").pathname;
    calls.push(path);
    return path === "/api/reports/member-stats" ? answer() : json(path === "/api/competitions" ? COMPETITIONS : []);
  });
  const auth = fakeAuth({ status: "signedIn", user: { uid: "u1", email: "u@alj.example" }, role: "coach" });
  mount(OutilsStatsPage, {
    attachTo: document.body,
    global: {
      provide: {
        ...provided(auth, api),
        [OUTILS_KEY]: { seasons: ref(["2026-2027", "2025-2026"]), initialSeason: ref("2026-2027"), toast: { show: vi.fn() } },
      },
    },
  });
  await flushPromises();
  const byId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  /** The rows of a chart's figures table, as "label: count". */
  const figures = (id: string) =>
    [...document.querySelectorAll(`[data-testid="${id}"] tbody tr`)].map((row) =>
      [...row.querySelectorAll("th, td")].map((cell) => cell.textContent.trim()).join(": "),
    );
  return { calls, byId, figures };
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("OutilsStatsPage, members", () => {
  it("shows the gender of the season's members, and another season without a new request", async () => {
    const { calls, byId, figures } = await render();

    expect(figures("chart-sex")).toEqual(["Hommes: 2", "Femmes: 1"]);

    const season = byId("stats-season") as HTMLSelectElement;
    season.value = "2025-2026";
    season.dispatchEvent(new Event("change"));
    await flushPromises();

    expect(figures("chart-sex")).toEqual(["Femmes: 1"]);
    expect(calls.filter((path) => path === "/api/reports/member-stats")).toHaveLength(1);
  });

  it("sums the season up on the cards", async () => {
    const { byId } = await render();

    expect(byId("card-members")!.textContent).toContain("3");
    expect(byId("card-new")!.textContent).toContain("0 %");
    expect(byId("card-women")).toBeNull();
  });

  it("opens the breakdown of a chart with « Détail », in counts or in percent of each bar", async () => {
    const { byId, figures } = await render();
    expect(byId("chart-sex-detail")).toBeNull();

    byId("detail-sex")!.click();
    await flushPromises();
    expect(figures("chart-sex-detail")).toEqual(["Adulte: 1: 2"]);

    byId("detail-sex-percent")!.click();
    await flushPromises();
    expect(figures("chart-sex-detail")).toEqual(["Adulte: 33 %: 67 %"]);

    byId("detail-sex")!.click();
    await flushPromises();
    expect(byId("chart-sex-detail")).toBeNull();
  });

  it("follows the members of every season by sex, with their total", async () => {
    const { figures } = await render();

    expect(figures("chart-seasons")).toEqual(["2025-2026: 1: 0: 1", "2026-2027: 1: 2: 3"]);
  });

  it("says the statistics need the network instead of showing empty charts", async () => {
    const { byId } = await render(() => Promise.reject(new TypeError("Failed to fetch")));

    expect(byId("member-stats-offline")!.textContent).toContain("hors ligne");
    expect(byId("chart-sex")).toBeNull();
  });
});

describe("OutilsStatsPage, competitions", () => {
  it("adds up the podiums of the last seasons", async () => {
    const { byId } = await render();

    expect(byId("kpi-podiums")!.textContent).toContain("3");
  });

  it("counts the competitions of the current season and their competitors", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-22T12:00:00") });
    const { byId } = await render();

    expect(byId("kpi-competitions")!.textContent).toContain("1");
    expect(byId("kpi-competitors")!.textContent).toContain("2");
    expect(byId("kpi-unique-competitors")!.textContent).toContain("2");
    expect(byId("kpi-budget")!.textContent).toContain("25,00");
  });

  it("charts the season's competitions per month", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-22T12:00:00") });
    const { figures } = await render();

    expect(figures("chart-competitions-per-month")).toContain("Oct.: 1");
  });
});
