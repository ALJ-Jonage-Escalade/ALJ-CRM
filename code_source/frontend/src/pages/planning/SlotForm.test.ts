import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { ref } from "vue";
import { draftOf, type Slot, type SlotDraft } from "./slots";
import SlotForm from "./SlotForm.vue";

const SLOT: Slot = {
  id: 7,
  groupe: "Autonome",
  type: "autonome",
  categorie_age: "Adultes",
  jour: "Lundi / Jeudi",
  horaires: "20:00 - 22:30",
  encadrants: [],
  helloasso_tarifs: ["Autonome 2025"],
  whatsapp_link: "",
  naissance_min: "",
  naissance_max: "",
};

function render(slot?: Slot, tarifs = ["Autonome adultes", "Licence sèche"]) {
  const draft = ref<SlotDraft>(draftOf(slot));
  const wrapper = mount(SlotForm, {
    props: { modelValue: draft.value, "onUpdate:modelValue": (v: SlotDraft) => (draft.value = v), tarifs },
  });
  const byId = (id: string) => wrapper.find(`[data-testid="${id}"]`);
  const tarif = (name: string) =>
    wrapper.findAll<HTMLInputElement>('[data-testid="slot-tarifs"] input').find((i) => i.element.value === name)!;
  return { wrapper, draft, byId, tarif };
}

describe("SlotForm", () => {
  it("fills a new slot and emits save", async () => {
    const { wrapper, draft, byId, tarif } = render();
    await byId("slot-groupe").setValue("Loisir collège");
    await byId("slot-jour").setValue("Mercredi");
    await byId("slot-type").setValue("compétition");
    await byId("slot-encadrants").setValue("Remus Lupin, Rubeus Hagrid");
    await tarif("Licence sèche").setValue(true);
    await wrapper.find("form").trigger("submit");
    expect(draft.value).toMatchObject({
      groupe: "Loisir collège",
      jour: "Mercredi",
      type: "compétition",
      encadrants: "Remus Lupin, Rubeus Hagrid",
      helloasso_tarifs: ["Licence sèche"],
    });
    expect(wrapper.emitted("save")).toHaveLength(1);
  });

  it("keeps the day and tariff a slot already has", () => {
    const { byId, tarif } = render(SLOT);
    expect((byId("slot-jour").element as HTMLSelectElement).value).toBe("Lundi / Jeudi");
    expect(tarif("Autonome 2025").element.checked).toBe(true);
    expect(tarif("Autonome adultes").element.checked).toBe(false);
  });

  it("refuses a slot without readable hours", async () => {
    const { wrapper, byId } = render(SLOT);
    await byId("slot-horaires").setValue("le soir");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("save")).toBeUndefined();
    expect(wrapper.emitted("invalid")).toEqual([["⚠️ Horaires illisibles : écrivez-les comme « 18:00 - 20:00 »."]]);
  });

  it("says when the season has no tariff", () => {
    const { byId } = render(undefined, []);
    expect(byId("slot-tarifs").text()).toContain("Aucun tarif de saison configuré");
  });

  it("cancels", async () => {
    const { wrapper, byId } = render();
    await byId("slot-cancel").trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});
