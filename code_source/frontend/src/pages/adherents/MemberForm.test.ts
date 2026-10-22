import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { nextTick, reactive } from "vue";
import MemberForm from "./MemberForm.vue";
import { member } from "./members.fixture";
import { draftOf, type MemberDraft } from "./record";

const TODAY = new Date(2026, 9, 22);
const TARIFS = [{ tarif: "Adulte loisir", detail: "Loisir adultes" }, { tarif: "Licence sèche", detail: "" }];

function render(draft: MemberDraft, adding: boolean) {
  const wrapper = mount(MemberForm, {
    attachTo: document.body,
    props: { modelValue: draft, "onUpdate:modelValue": () => {}, adding, tarifs: TARIFS, today: TODAY },
  });
  const field = (name: string) => wrapper.find(`[data-testid="member-${name}"]`);
  const error = (name: string) => wrapper.find(`#member-${name}-error`);
  return { wrapper, field, error };
}

describe("MemberForm validation", () => {
  it("adding: shows each missing field under it, focuses the first one, and does not save", async () => {
    const { wrapper, field, error } = render(draftOf(undefined, ""), true);
    await wrapper.find("form").trigger("submit");
    await nextTick();
    expect(error("last_name").text()).toBe("Le nom est obligatoire.");
    expect(error("first_name").text()).toBe("Le prénom est obligatoire.");
    expect(error("birth_date").text()).toBe("La date de naissance est obligatoire.");
    expect(wrapper.find('[data-testid="member-tarif-error"]').text()).toBe("Choisissez un groupe (tarif).");
    expect(field("last_name").attributes("aria-invalid")).toBe("true");
    expect(field("last_name").attributes("aria-describedby")).toBe("member-last_name-error");
    expect(document.activeElement).toBe(field("last_name").element);
    expect(wrapper.emitted("save")).toBeUndefined();
    wrapper.unmount();
  });

  it("adding: refuses a birth date in the future or that does not exist, and a negative amount", async () => {
    const d = { ...draftOf(undefined, "Adulte loisir"), last_name: "DUPONT", first_name: "Léa", birth_date: "2030-01-01", amount: "-5" };
    const { wrapper, error } = render(d, true);
    await wrapper.find("form").trigger("submit");
    expect(error("birth_date").text()).toBe("Date de naissance invalide.");
    expect(error("amount").text()).toBe("Montant invalide (nombre positif).");
    wrapper.unmount();
  });

  it("editing: checks e-mails and phone, clears a message once the field is corrected, then saves", async () => {
    const d = reactive({ ...draftOf(member({ tarif_name: "Adulte loisir" })), email_primary: "pas-une-adresse", phone: "12" });
    const { wrapper, field, error } = render(d, false);
    expect(field("last_name").exists()).toBe(false);  // identity is not edited
    await wrapper.find("form").trigger("submit");
    expect(error("email_primary").text()).toBe("Adresse e-mail invalide.");
    expect(error("phone").text()).toBe("Numéro de téléphone invalide.");

    d.email_primary = "lea@example.org";
    await nextTick();
    expect(error("email_primary").exists()).toBe(false);
    expect(error("phone").exists()).toBe(true);

    d.phone = "+33 6 12 34 56 78";
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("save")).toHaveLength(1);
    wrapper.unmount();
  });

  it("keeps a status and a tariff that are not among the choices", () => {
    const d = draftOf(member({ status_norm: "Payé", tarif_name: "Tarif 2024" }));
    const { field, wrapper } = render(d, false);
    expect((field("status").element as HTMLSelectElement).value).toBe("Payé");
    expect(wrapper.find('[data-testid="member-tarifs"]').text()).toContain("Tarif 2024");
    wrapper.unmount();
  });
});
