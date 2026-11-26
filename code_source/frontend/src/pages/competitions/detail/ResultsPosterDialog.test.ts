import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ResultsPosterDialog from "./ResultsPosterDialog.vue";
import type { Competition, Participant } from "../competitions";
import { WIDE_LAYOUT_QUERY } from "../../../composables/media";

// Drawing the PNG needs a real canvas, which jsdom lacks: the library is the boundary faked here
vi.mock("modern-screenshot", () => ({ domToBlob: vi.fn(() => Promise.resolve(new Blob(["png"], { type: "image/png" }))) }));

const competition: Competition = { id: 7, nom: "Coupe régionale de bloc", date_competition: "2026-12-14", lieu: "Villeurbanne" };
const participants: Participant[] = [{ nom: "BASSO", prenom: "Chloé", categorie_ffme: "U13 Femme", classement: "1", total_categorie: 25 }];

function useLayout(wide: boolean): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === WIDE_LAYOUT_QUERY && wide,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

async function openDialog(): Promise<void> {
  mount(ResultsPosterDialog, { props: { open: true, competition, participants }, attachTo: document.body });
  await flushPromises();
}

const byTestId = (id: string): HTMLElement | null => document.querySelector(`[data-testid="${id}"]`);

describe("ResultsPosterDialog", () => {
  beforeEach(() => {
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:poster", revokeObjectURL: () => undefined }));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("shows the image and downloads it on a computer, without sharing", async () => {
    useLayout(true);
    vi.stubGlobal("navigator", { ...navigator, canShare: () => true, share: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe("resultats_Coupe_regionale_de_bloc_2026-12-14.png");
    });
    await openDialog();

    expect(byTestId("poster-preview")?.getAttribute("src")).toBe("blob:poster");
    expect(byTestId("poster-share")).toBeNull();
    byTestId("poster-download")?.click();
    expect(click).toHaveBeenCalledOnce();
  });

  it("shares the image on a phone that can share files", async () => {
    useLayout(false);
    const share = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, canShare: () => true, share });
    await openDialog();

    byTestId("poster-share")?.click();
    await flushPromises();

    expect(share).toHaveBeenCalledOnce();
    const [data] = share.mock.calls[0] as unknown as [ShareData];
    expect(data.files?.[0]?.name).toBe("resultats_Coupe_regionale_de_bloc_2026-12-14.png");
    expect(data.files?.[0]?.type).toBe("image/png");
  });

  it("only downloads on a phone that cannot share files", async () => {
    useLayout(false);
    vi.stubGlobal("navigator", { ...navigator, canShare: () => false });
    await openDialog();

    expect(byTestId("poster-share")).toBeNull();
    expect(byTestId("poster-download")).not.toBeNull();
  });
});
