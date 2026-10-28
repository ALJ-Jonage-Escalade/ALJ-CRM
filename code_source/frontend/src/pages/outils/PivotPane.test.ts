import { flushPromises, mount } from "@vue/test-utils";
import { VuePivottableUi } from "vue-pivottable";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API_KEY, type ApiFetch } from "../../lib/api";
import { CLIENT_KEY, createApiClient, type Schemas } from "../../lib/client";
import PivotPane from "./PivotPane.vue";
import { DEFAULT_LAYOUT, LAYOUT_KEY, restoreLayout } from "./pivotLayout";

const HOSTILE = `<img src=x onerror="window.hacked=1"><b>`;

function record(fields: Partial<Schemas["PivotRecord"]>): Schemas["PivotRecord"] {
  return {
    Nom: "WEASLEY",
    Prénom: "Ron",
    Sexe: "H",
    Âge: 16,
    "Tranche d'Âge": "10 à 17 ans",
    Ville: "Jonage",
    "Groupe / Tarif": "Loisir",
    Statut: "Validé",
    Saison: "2026-2027",
    "Type d'Adhésion": "Déjà Membre",
    "Date d'Inscription": "2026-06-03",
    "Mois d'Inscription": "2026-06",
    ...fields,
  };
}

const RECORDS = [
  record({}),
  record({ Nom: "GRANGER", Sexe: "F" }),
  record({ "Groupe / Tarif": HOSTILE, Âge: null }),
  record({ Statut: "Annulé" }), // hidden by default
  record({ "Groupe / Tarif": "Liste d'attente cours" }), // hidden by default
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

async function render(answer: (season: string) => Response | Promise<Response> = (season) => json({ season, records: RECORDS })) {
  const seasons: string[] = [];
  const api: ApiFetch = vi.fn(async (url: string) => {
    const season = new URL(url, "http://alj.test").searchParams.get("season") ?? "";
    seasons.push(season);
    return answer(season);
  });
  const wrapper = mount(PivotPane, {
    attachTo: document.body,
    props: { season: "2026-2027" },
    global: { provide: { [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") } },
  });
  await flushPromises();
  const table = () => wrapper.findComponent(VuePivottableUi);
  const text = () => wrapper.get('[data-testid="pivot-table"] table.pvtTable').text();
  return { wrapper, seasons, table, text };
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  document.body.innerHTML = "";
});

describe("PivotPane", () => {
  it("counts the members of the season by group, status and sex, without the hidden values", async () => {
    const { seasons, table, text } = await render();
    expect(seasons).toEqual(["2026-2027"]);
    expect(table().props("pivotModel")).toMatchObject({
      ...DEFAULT_LAYOUT,
      valueFilter: { "Groupe / Tarif": { "Liste d'attente cours": true }, Statut: { Annulé: true } },
    });
    // Rows: the groups; columns: Validé × Femme / Homme, then the totals
    expect(text()).toBe(`StatutValidéTotauxSexeFemmeHommeGroupe / Tarif${HOSTILE}11Loisir112Totaux123`);
    expect(text()).not.toContain("Liste d'attente cours");
    expect(text()).not.toContain("Annulé");
  });

  it("shows member values as text", async () => {
    const { wrapper, text } = await render();
    expect(text()).toContain(HOSTILE);
    expect(wrapper.get('[data-testid="pivot-table"]').element.querySelectorAll("img, b")).toHaveLength(0);
    expect("hacked" in window).toBe(false);
  });

  it("keeps the layout for another season and resets the value filters", async () => {
    const { wrapper, seasons, table } = await render();
    const layout = { ...DEFAULT_LAYOUT, rows: ["Ville"], cols: [], aggregatorName: "Âge moyen" };
    table().vm.$emit("update:pivotModel", { ...layout, valueFilter: { Ville: { Jonage: true } } });
    await flushPromises();
    expect(table().props("pivotModel")).toMatchObject({ valueFilter: { Ville: { Jonage: true } } });

    await wrapper.setProps({ season: "Toutes les saisons" });
    await flushPromises();
    expect(seasons).toEqual(["2026-2027", "Toutes les saisons"]);
    expect(table().props("pivotModel")).toEqual({
      ...layout,
      valueFilter: { "Groupe / Tarif": { "Liste d'attente cours": true }, Statut: { Annulé: true } },
    });
  });

  it("stores the layout, reads it back on the next visit, and resets it", async () => {
    const first = await render();
    const layout = { ...DEFAULT_LAYOUT, rows: ["Tranche d'Âge"], rendererName: "Carte de chaleur" };
    first.table().vm.$emit("update:pivotModel", { ...layout, valueFilter: { Sexe: { Femme: true } } });
    expect(JSON.parse(localStorage.getItem(LAYOUT_KEY) ?? "")).toEqual(layout);
    first.wrapper.unmount();

    const second = await render();
    expect(second.table().props("pivotModel")).toEqual({
      ...layout,
      valueFilter: { "Groupe / Tarif": { "Liste d'attente cours": true }, Statut: { Annulé: true } },
    });
    await second.wrapper.get('[data-testid="pivot-reset"]').trigger("click");
    expect(restoreLayout(localStorage.getItem(LAYOUT_KEY))).toEqual(DEFAULT_LAYOUT);
    expect(second.table().props("pivotModel")).toMatchObject(DEFAULT_LAYOUT);
  });

  it("says when the members cannot be loaded", async () => {
    const { wrapper } = await render(() => json({ status: "error", message: "Erreur interne" }, 500));
    expect(wrapper.get('[data-testid="pivot-status"]').text()).toBe(
      "❌ Impossible de charger le tableau croisé dynamique : Erreur interne",
    );
    expect(wrapper.find('[data-testid="pivot-table"]').exists()).toBe(false);
  });

  it("says when the server cannot be reached (offline)", async () => {
    const { wrapper } = await render(() => Promise.reject(new TypeError("Failed to fetch")));
    expect(wrapper.get('[data-testid="pivot-status"]').text()).toBe(
      "❌ Impossible de charger le tableau croisé dynamique : Serveur injoignable : vérifiez la connexion réseau.",
    );
  });
});
