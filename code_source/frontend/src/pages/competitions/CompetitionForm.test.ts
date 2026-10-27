import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { CLIENT_KEY } from "../../lib/client";
import CompetitionForm from "./CompetitionForm.vue";

function createMockClient(mockLookup: (id: string) => Promise<unknown>) {
  return {
    GET: vi.fn(async (path: string, options?: { params?: { path?: { id_ffme?: string } } }) => {
      if (path === "/api/competitions/lookup-ffme/{id_ffme}") {
        const id = options?.params?.path?.id_ffme ?? "";
        try {
          const data = await mockLookup(id);
          return { data, error: undefined, response: new Response() };
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : String(err);
          return { data: undefined, error: { message: message || "Not found" }, response: new Response(null, { status: 404 }) };
        }
      }
      return { data: undefined, error: { message: "Route unknown" }, response: new Response(null, { status: 404 }) };
    }),
    POST: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  };
}

describe("CompetitionForm", () => {
  it("places id_ffme before nom in the form layout", () => {
    const wrapper = mount(CompetitionForm, {
      props: { coaches: [], busy: false },
      global: {
        provide: {
          [CLIENT_KEY as symbol]: createMockClient(async () => ({})),
        },
      },
    });

    const inputs = wrapper.findAll("input");
    const idIndex = inputs.findIndex((i) => i.attributes("data-testid") === "cf-idffme");
    const nomIndex = inputs.findIndex((i) => i.attributes("data-testid") === "cf-nom");
    expect(idIndex).toBeGreaterThanOrEqual(0);
    expect(nomIndex).toBeGreaterThan(idIndex);
  });

  it("disables lookup button when id_ffme is empty", () => {
    const wrapper = mount(CompetitionForm, {
      props: { coaches: [], busy: false },
      global: {
        provide: {
          [CLIENT_KEY as symbol]: createMockClient(async () => ({})),
        },
      },
    });

    const btn = wrapper.get('[data-testid="cf-lookup-btn"]');
    expect((btn.element as HTMLButtonElement).disabled).toBe(true);
  });

  it("fetches competition details and prefills nom, date, lieu, and type", async () => {
    const mockLookup = vi.fn(async (id: string) => ({
      id_ffme: id,
      nom: "Coupe régionale de bloc Cusset Vichy",
      date_competition: "2026-11-07",
      date_fin: "2026-11-07",
      lieu: "CUSSET",
      type: "Bloc",
    }));

    const wrapper = mount(CompetitionForm, {
      props: { coaches: [], busy: false },
      global: {
        provide: {
          [CLIENT_KEY as symbol]: createMockClient(mockLookup),
        },
      },
    });

    const idInput = wrapper.get('[data-testid="cf-idffme"]');
    await idInput.setValue("18896");

    const btn = wrapper.get('[data-testid="cf-lookup-btn"]');
    expect((btn.element as HTMLButtonElement).disabled).toBe(false);

    await btn.trigger("click");
    await flushPromises();

    expect(mockLookup).toHaveBeenCalledWith("18896");

    const nomInput = wrapper.get('[data-testid="cf-nom"]');
    expect((nomInput.element as HTMLInputElement).value).toBe("Coupe régionale de bloc Cusset Vichy");

    const dateInput = wrapper.get('[data-testid="cf-date"]');
    expect((dateInput.element as HTMLInputElement).value).toBe("2026-11-07");

    const dateFinInput = wrapper.get('[data-testid="cf-date-fin"]');
    expect((dateFinInput.element as HTMLInputElement).value).toBe("2026-11-07");

    const lieuInput = wrapper.get('[data-testid="cf-lieu"]');
    expect((lieuInput.element as HTMLInputElement).value).toBe("CUSSET");

    const typeSelect = wrapper.get('[data-testid="cf-type"]');
    expect((typeSelect.element as HTMLSelectElement).value).toBe("Bloc");

    const successMsg = wrapper.get('[data-testid="cf-lookup-success"]');
    expect(successMsg.text()).toContain("Coupe régionale de bloc Cusset Vichy");
  });

  it("prefills distinct start and end dates for a two-day competition", async () => {
    const mockLookup = vi.fn(async (id: string) => ({
      id_ffme: id,
      nom: "Championnat départemental de bloc Dordogne et Gironde",
      date_competition: "2026-10-31",
      date_fin: "2026-11-01",
      lieu: "PAREMPUYRE",
      type: "Bloc",
    }));

    const wrapper = mount(CompetitionForm, {
      props: { coaches: [], busy: false },
      global: {
        provide: {
          [CLIENT_KEY as symbol]: createMockClient(mockLookup),
        },
      },
    });

    await wrapper.get('[data-testid="cf-idffme"]').setValue("18849");
    await wrapper.get('[data-testid="cf-lookup-btn"]').trigger("click");
    await flushPromises();

    expect((wrapper.get('[data-testid="cf-date"]').element as HTMLInputElement).value).toBe("2026-10-31");
    expect((wrapper.get('[data-testid="cf-date-fin"]').element as HTMLInputElement).value).toBe("2026-11-01");
  });

  it("displays an error message when the competition is not found", async () => {
    const mockLookup = vi.fn(async () => {
      throw new Error("Compétition n°99999 introuvable sur MyCompet FFME.");
    });

    const wrapper = mount(CompetitionForm, {
      props: { coaches: [], busy: false },
      global: {
        provide: {
          [CLIENT_KEY as symbol]: createMockClient(mockLookup),
        },
      },
    });

    await wrapper.get('[data-testid="cf-idffme"]').setValue("99999");
    await wrapper.get('[data-testid="cf-lookup-btn"]').trigger("click");
    await flushPromises();

    const errorMsg = wrapper.get('[data-testid="cf-lookup-error"]');
    expect(errorMsg.text()).toContain("introuvable sur MyCompet");
  });
});
