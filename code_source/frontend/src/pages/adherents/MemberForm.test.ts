import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { nextTick, reactive } from "vue";
import MemberForm from "./MemberForm.vue";
import { member } from "./members.fixture";
import { draftOf, type MemberDraft } from "./record";

const TODAY = new Date(2026, 9, 22);
const TARIFS = [
  { tarif: "Adulte loisir", detail: "Loisir adultes" },
  { tarif: "Licence sèche", detail: "" },
];

function render(draft: MemberDraft, adding: boolean) {
  const wrapper = mount(MemberForm, {
    attachTo: document.body,
    props: { modelValue: draft, "onUpdate:modelValue": () => {}, adding, tarifs: TARIFS, today: TODAY },
  });
  const field = (name: string) => wrapper.find(`[data-testid="member-${name}"]`);
  const error = (name: string) => wrapper.find(`#member-${name}-error`);
  return { wrapper, field, error };
}

describe("MemberForm emergency contacts", () => {
  const CONTACTS = [
    { name: "Marie", phone: "06 01 01 01 01" },
    { name: "Paul", phone: "06 02 02 02 02" },
    { name: "Anna", phone: "06 03 03 03 03" },
  ];

  function renderContacts() {
    const draft = reactive(
      draftOf(member({ first_name: "Léa", last_name: "DUPONT", tarif_name: "Adulte loisir", emergency_contacts: CONTACTS })),
    );
    const { wrapper } = render(draft, false);
    const rows = () => wrapper.findAll('[data-testid="contact-row"]');
    const names = () => rows().map((r) => (r.find('[data-testid="contact-name"]').element as HTMLInputElement).value);
    return { wrapper, draft, rows, names };
  }

  it("labels the first row as the main contact and numbers the others", () => {
    const { wrapper, rows } = renderContacts();
    expect(rows().map((r) => r.find('[data-testid="contact-label"]').text())).toEqual(["Principal", "Contact 2", "Contact 3"]);
    wrapper.unmount();
  });

  it("adds any number of rows and focuses the new one", async () => {
    const { wrapper, rows } = renderContacts();
    await wrapper.find('[data-testid="contact-add"]').trigger("click");
    await wrapper.find('[data-testid="contact-add"]').trigger("click");
    await nextTick();
    expect(rows()).toHaveLength(5);
    expect(document.activeElement).toBe(rows()[4]!.find('[data-testid="contact-name"]').element);
    wrapper.unmount();
  });

  it("moves a row, keeps its values and the focus on the button pressed", async () => {
    const { wrapper, rows, names, draft } = renderContacts();
    await rows()[2]!.find('[data-testid="contact-up"]').trigger("click");
    await nextTick();
    expect(names()).toEqual(["Marie", "Anna", "Paul"]);
    expect(draft.emergency_contacts.map((r) => r.phone)).toEqual(["06 01 01 01 01", "06 03 03 03 03", "06 02 02 02 02"]);
    expect(document.activeElement).toBe(rows()[1]!.find('[data-testid="contact-up"]').element);

    // Up to the first row: its ↑ is gone, the focus goes to its ↓
    await rows()[1]!.find('[data-testid="contact-up"]').trigger("click");
    await nextTick();
    expect(names()).toEqual(["Anna", "Marie", "Paul"]);
    expect(document.activeElement).toBe(rows()[0]!.find('[data-testid="contact-down"]').element);
    wrapper.unmount();
  });

  it("offers no ↑ on the first row and no ↓ on the last, and names every button", () => {
    const { wrapper, rows } = renderContacts();
    expect(rows()[0]!.find('[data-testid="contact-up"]').exists()).toBe(false);
    expect(rows()[0]!.find('[data-testid="contact-down"]').exists()).toBe(true);
    expect(rows()[2]!.find('[data-testid="contact-down"]').exists()).toBe(false);
    expect(rows()[1]!.find('[data-testid="contact-remove"]').attributes("aria-label")).toBe("Supprimer le contact 2");
    expect(rows()[1]!.find('[data-testid="contact-up"]').attributes("aria-label")).toBe("Monter le contact 2");
    expect(rows()[1]!.find('[data-testid="contact-down"]').attributes("aria-label")).toBe("Descendre le contact 2");
    wrapper.unmount();
  });

  it("removes a row", async () => {
    const { wrapper, rows, names } = renderContacts();
    await rows()[0]!.find('[data-testid="contact-remove"]').trigger("click");
    await nextTick();
    expect(names()).toEqual(["Paul", "Anna"]);
    expect(rows()[0]!.find('[data-testid="contact-label"]').text()).toBe("Principal");
    expect(document.activeElement).toBe(wrapper.find('[data-testid="contact-add"]').element);
    wrapper.unmount();
  });

  it("shows an invalid phone under its row, focuses it and does not save", async () => {
    const { wrapper, rows, draft } = renderContacts();
    await rows()[1]!.find('[data-testid="contact-phone"]').setValue("12");
    await wrapper.find("form").trigger("submit");
    await nextTick();
    expect(rows()[1]!.text()).toContain("Numéro de téléphone invalide.");
    expect(rows()[0]!.text()).not.toContain("Numéro de téléphone invalide.");
    expect(document.activeElement).toBe(rows()[1]!.find('[data-testid="contact-phone"]').element);
    expect(wrapper.emitted("save")).toBeUndefined();

    draft.emergency_contacts[1]!.phone = "06 02 02 02 02";
    await nextTick();
    expect(rows()[1]!.text()).not.toContain("Numéro de téléphone invalide.");
    wrapper.unmount();
  });
});

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
    const d = reactive({
      ...draftOf(member({ last_name: "DUPONT", first_name: "Léa", tarif_name: "Adulte loisir" })),
      email_primary: "pas-une-adresse",
      phone: "12",
    });
    const { wrapper, field, error } = render(d, false);
    expect(field("last_name").exists()).toBe(true); // identity is now editable
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

  it("editing: refuses to empty an amount already recorded, which the server would keep", async () => {
    const d = reactive(draftOf(member({ last_name: "DUPONT", first_name: "Léa", tarif_name: "Adulte loisir", amount: 120 })));
    const { wrapper, error } = render(d, false);
    d.amount = "";
    await wrapper.find("form").trigger("submit");
    expect(error("amount").text()).toBe("Le montant ne peut pas être vidé : indiquez 0 si rien n'a été réglé.");
    expect(wrapper.emitted("save")).toBeUndefined();
    d.amount = "0";
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
