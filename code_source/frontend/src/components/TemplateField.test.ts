import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import TemplateField from "./TemplateField.vue";
import { dialogs } from "../composables/dialogs";

function render(text = "Bonjour X !", props: Record<string, unknown> = {}) {
  const value = ref(text);
  const wrapper = mount(TemplateField, {
    props: {
      id: "body",
      label: "Corps du message",
      multiline: true,
      modelValue: value.value,
      "onUpdate:modelValue": (v: string) => {
        value.value = v;
        void wrapper.setProps({ modelValue: v });
      },
      ...props,
    },
    attachTo: document.body,
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  const area = () => byId("body").element as HTMLTextAreaElement;
  return { wrapper, value, byId, area };
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("TemplateField", () => {
  it("inserts a variable's label at the cursor", async () => {
    const { byId, area, value } = render();
    area().setSelectionRange(8, 9); // the X
    await byId("body-variables-toggle").trigger("click");
    const button = byId("body-variables")
      .findAll("button")
      .find((b) => b.text() === "{Prénom}")!;
    await button.trigger("click");
    await nextTick();
    expect(value.value).toBe("Bonjour {Prénom} !");
    expect([area().selectionStart, area().selectionEnd]).toEqual([16, 16]);
  });

  it("offers every variable without a kind", async () => {
    const { byId } = render();
    await byId("body-variables-toggle").trigger("click");
    const labels = byId("body-variables")
      .findAll("button")
      .map((b) => b.text());
    expect(labels).toContain("{Montant de l'adhésion}");
    expect(labels).toContain("{Lien WhatsApp}");
  });

  it("shows why a variable is unknown, under the field", async () => {
    const { byId, wrapper } = render("Bonjour {Prénom}");
    expect(byId("body-error").exists()).toBe(false);
    await wrapper.setProps({ modelValue: "Bonjour {Prenon}" });
    expect(byId("body-error").text()).toContain("Variable inconnue : {Prenon}.");
    expect(byId("body-error").text()).toContain("{Prénom}");
  });

  it("wraps the selection in tags, and keeps it selected", async () => {
    const { byId, area, value } = render();
    area().setSelectionRange(0, 7);
    await byId("body-format-bold").trigger("click");
    await nextTick();
    expect(value.value).toBe("<b>Bonjour</b> X !");
    expect([area().selectionStart, area().selectionEnd]).toEqual([3, 10]);
  });

  it("adds a link to the address given, or nothing", async () => {
    const ask = vi.spyOn(dialogs, "prompt").mockResolvedValueOnce("https://www.alj-escalade.fr").mockResolvedValueOnce("https://");
    const { byId, area, value } = render("");
    area().setSelectionRange(0, 0);
    await byId("body-format-link").trigger("click");
    await nextTick();
    expect(value.value).toBe('<a href="https://www.alj-escalade.fr">texte</a>');
    await byId("body-format-link").trigger("click");
    await nextTick();
    expect(value.value).toBe('<a href="https://www.alj-escalade.fr">texte</a>');
    expect(ask).toHaveBeenCalledTimes(2);
  });

  it("has no formatting toolbar on a one-line field", () => {
    const { byId } = render("Sujet", { id: "subject", multiline: false });
    expect((byId("subject").element as HTMLInputElement).tagName).toBe("INPUT");
    expect(byId("subject-format-bold").exists()).toBe(false);
  });
});
