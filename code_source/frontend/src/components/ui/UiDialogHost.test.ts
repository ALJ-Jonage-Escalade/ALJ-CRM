import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { cancelDialog, dialogs } from "../../composables/dialogs";
import UiDialog from "./UiDialog.vue";
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

  // Dialogs share one z-index: the one later in <body> is on top, whatever was opened and closed before
  it("stays on top of a page dialog opened after an earlier confirmation", async () => {
    render();
    const openPageDialog = (): VueWrapper =>
      mount(UiDialog, { props: { title: "Attestation", open: true }, attrs: { "data-testid": "page-dialog" }, attachTo: document.body });

    const firstPageDialog = openPageDialog();
    await flushPromises();
    const firstAnswer = dialogs.confirm({ title: "Envoyer" });
    await flushPromises();
    byId("dialog-confirm")!.click();
    expect(await firstAnswer).toBe(true);
    await flushPromises();
    firstPageDialog.unmount();

    const secondPageDialog = openPageDialog();
    await flushPromises();
    const secondAnswer = dialogs.confirm({ title: "Envoyer" });
    await flushPromises();
    const position = byId("page-dialog")!.compareDocumentPosition(byId("dialog-host")!);
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    cancelDialog();
    expect(await secondAnswer).toBe(false);
    secondPageDialog.unmount();
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
