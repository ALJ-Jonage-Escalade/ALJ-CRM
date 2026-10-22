import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import type { Template } from "./editor";
import TemplateForm from "./TemplateForm.vue";

const TEMPLATE: Template = {
  name: "Relance",
  subject: "Inscription",
  body: "Bonjour X !",
  sender_email: "competitions@alj-escalade.fr",
  sender_name: "ALJ Compétitions",
};

function render(template: Partial<Template> = {}) {
  const draft = ref<Template>({ ...TEMPLATE, ...template });
  const wrapper = mount(TemplateForm, {
    props: { modelValue: draft.value, "onUpdate:modelValue": (v: Template) => (draft.value = v) },
    attachTo: document.body,
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  const body = () => byId("body").element as HTMLTextAreaElement;
  return { wrapper, draft, byId, body };
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("TemplateForm", () => {
  it("edits the template", async () => {
    const { byId, draft } = render();
    await byId("subject").setValue("Licence {num_licence}");
    await byId("sender-name").setValue("ALJ");
    expect(draft.value).toMatchObject({ subject: "Licence {num_licence}", sender_name: "ALJ" });
  });

  it("emits save for a valid template", async () => {
    const { wrapper } = render();
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("save")).toHaveLength(1);
    expect(wrapper.emitted("invalid")).toBeUndefined();
  });

  it.each([
    [{ name: "  " }, "⚠️ Le titre du modèle ne peut pas être vide."],
    [{ subject: "" }, "⚠️ Le sujet et le corps du message sont obligatoires."],
    [{ body: "" }, "⚠️ Le sujet et le corps du message sont obligatoires."],
    [{ sender_email: "pas-une-adresse" }, "⚠️ L'adresse d'expédition doit être une adresse e-mail valide."],
  ])("refuses %j", async (change, message) => {
    const { wrapper } = render(change);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("save")).toBeUndefined();
    expect(wrapper.emitted("invalid")).toEqual([[message]]);
  });

  it("inserts a variable at the cursor", async () => {
    const { byId, body, draft } = render();
    body().setSelectionRange(8, 9);  // the X
    await byId("variables-toggle").trigger("click");
    const button = byId("variables").findAll("button").find((b) => b.text() === "{first_name}")!;
    await button.trigger("click");
    await nextTick();
    expect(draft.value.body).toBe("Bonjour {first_name} !");
    expect([body().selectionStart, body().selectionEnd]).toEqual([20, 20]);
  });

  it("wraps the selection in tags, and keeps it selected", async () => {
    const { byId, body, draft } = render();
    body().setSelectionRange(0, 7);
    await byId("format-bold").trigger("click");
    await nextTick();
    expect(draft.value.body).toBe("<b>Bonjour</b> X !");
    expect([body().selectionStart, body().selectionEnd]).toEqual([3, 10]);
  });

  it("adds a link to the address given, or nothing", async () => {
    const ask = vi.spyOn(window, "prompt").mockReturnValueOnce("https://www.alj-escalade.fr").mockReturnValueOnce("https://");
    const { byId, body, draft } = render({ body: "" });
    body().setSelectionRange(0, 0);
    await byId("format-link").trigger("click");
    await nextTick();
    expect(draft.value.body).toBe('<a href="https://www.alj-escalade.fr">texte</a>');
    await byId("format-link").trigger("click");
    await nextTick();
    expect(draft.value.body).toBe('<a href="https://www.alj-escalade.fr">texte</a>');
    expect(ask).toHaveBeenCalledTimes(2);
  });

  it("shows the busy save button", () => {
    const wrapper = mount(TemplateForm, { props: { modelValue: { ...TEMPLATE }, saving: true } });
    const save = wrapper.find('[data-testid="template-save"]');
    expect(save.text()).toBe("⏳ Enregistrement…");
    expect(save.attributes("disabled")).toBeDefined();
  });
});
