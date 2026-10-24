import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { cancelDialog, dialogs } from "../../composables/dialogs";
import UiDialogHost from "./UiDialogHost.vue";

const byId = <T extends HTMLElement = HTMLElement>(id: string): T | null => document.querySelector<T>(`[data-testid="${id}"]`);

let host: VueWrapper | undefined;

function render(): void {
  host = mount(UiDialogHost, { attachTo: document.body });
}

afterEach(() => {
  cancelDialog();
  host?.unmount();
  document.body.innerHTML = "";
});

describe("UiDialogHost", () => {
  it("shows the confirmation and answers true on the main button", async () => {
    render();
    const answer = dialogs.confirm({ title: "Supprimer le coach", message: "Supprimer ?\n(définitivement)", confirmLabel: "Supprimer" });
    await flushPromises();
    expect(byId("dialog-host")!.textContent).toContain("Supprimer le coach");
    expect(byId("dialog-message")!.textContent.trim()).toBe("Supprimer ?\n(définitivement)");
    expect(byId("dialog-confirm")!.textContent.trim()).toBe("Supprimer");
    byId("dialog-confirm")!.click();
    expect(await answer).toBe(true);
  });

  it("answers false on « Annuler »", async () => {
    render();
    const answer = dialogs.confirm({ title: "Archiver" });
    await flushPromises();
    expect(byId("dialog-confirm")!.textContent.trim()).toBe("Confirmer");
    byId("dialog-cancel")!.click();
    expect(await answer).toBe(false);
  });

  it("cancels the open request when another one comes", async () => {
    render();
    const first = dialogs.confirm({ title: "Premier" });
    const second = dialogs.confirm({ title: "Second" });
    expect(await first).toBe(false);
    await flushPromises();
    expect(byId("dialog-host")!.textContent).toContain("Second");
    byId("dialog-confirm")!.click();
    expect(await second).toBe(true);
  });

  it("returns the text entered, or null when cancelled", async () => {
    render();
    const entered = dialogs.prompt({ title: "Insérer un lien", label: "URL", value: "https://" });
    await flushPromises();
    const input = byId<HTMLInputElement>("dialog-input")!;
    expect(input.value).toBe("https://");
    input.value = "https://www.alj-escalade.fr";
    input.dispatchEvent(new Event("input"));
    byId("dialog-confirm")!.click();
    expect(await entered).toBe("https://www.alj-escalade.fr");

    const cancelled = dialogs.prompt({ title: "Insérer un lien", label: "URL" });
    await flushPromises();
    byId("dialog-cancel")!.click();
    expect(await cancelled).toBeNull();
  });
});
