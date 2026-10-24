import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import UiMenu from "./UiMenu.vue";
import UiMenuItem from "./UiMenuItem.vue";

const byId = <T extends HTMLElement = HTMLElement>(id: string): T | null => document.querySelector<T>(`[data-testid="${id}"]`);

let host: VueWrapper | undefined;

function render(onExport: () => void, onDelete: () => void, busy: string | false = false): void {
  const Page = defineComponent(
    () => () =>
      h(UiMenu, { label: "⋯ Plus", busy, "data-testid": "more" }, () => [
        h(UiMenuItem, { "data-testid": "export", onSelect: onExport }, () => "📥 Export"),
        h(UiMenuItem, { "data-testid": "delete", danger: true, disabled: true, onSelect: onDelete }, () => "🗑️ Supprimer"),
      ]),
  );
  host = mount(Page, { attachTo: document.body });
}

// Reka UI opens the menu on pointerdown (left button) or on the keyboard, not on a bare click
async function openMenu(): Promise<void> {
  byId("more")!.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await flushPromises();
}

afterEach(() => {
  host?.unmount();
  document.body.innerHTML = "";
});

describe("UiMenu", () => {
  it("keeps its items hidden until the button opens it", async () => {
    render(vi.fn(), vi.fn());
    expect(byId("more")!.textContent.trim()).toBe("⋯ Plus ▾");
    expect(byId("export")).toBeNull();
    await openMenu();
    expect(byId("export")!.textContent.trim()).toBe("📥 Export");
  });

  it("runs the chosen action and closes", async () => {
    const onExport = vi.fn();
    render(onExport, vi.fn());
    await openMenu();
    byId("export")!.click();
    await flushPromises();
    expect(onExport).toHaveBeenCalledOnce();
    expect(byId("export")).toBeNull();
  });

  it("marks a destructive action and does not run a disabled one", async () => {
    const onDelete = vi.fn();
    render(vi.fn(), onDelete);
    await openMenu();
    const remove = byId("delete")!;
    expect(remove.className).toContain("text-red-600");
    expect(remove.hasAttribute("data-disabled")).toBe(true);
    remove.click();
    await flushPromises();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("shows on its button that an action is in progress", () => {
    render(vi.fn(), vi.fn(), "Recherche…");
    const button = byId<HTMLButtonElement>("more")!;
    expect(button.textContent.trim()).toBe("⏳ Recherche…");
    expect(button.disabled).toBe(true);
  });
});
