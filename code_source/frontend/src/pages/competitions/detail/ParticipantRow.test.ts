import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ParticipantRow from "./ParticipantRow.vue";
import type { Row } from "../competitions";

describe("ParticipantRow", () => {
  const row: Row = {
    adherent_id: 1,
    nom: "DUPONT",
    prenom: "Lucas",
    num_licence: "123456",
    tarif: "Compétition U18",
    group: "Compétition U18",
    section: "U17 H",
    selectionne: true,
    present: false,
    statut_paiement: "en_attente",
    montant_paye: 0,
    commande_helloasso: "",
    note_paiement: "",
    urgence_nom: "",
    urgence_tel: "",
    phone: "0601020304",
    email: "lucas@test.fr",
    emergency: [],
    queued: { selectionne: false, present: false },
    contacts: [],
  };

  it("renders a clickable button for athlete name when contactsShown is true and emits showContact", async () => {
    const wrapper = mount(ParticipantRow, {
      props: {
        row,
        canWrite: true,
        staff: true,
        contactsShown: true,
      },
    });

    const nameBtn = wrapper.find("button[data-testid='participant-name']");
    expect(nameBtn.exists()).toBe(true);
    expect(nameBtn.text()).toBe("DUPONT Lucas");

    await nameBtn.trigger("click");
    expect(wrapper.emitted("showContact")).toHaveLength(1);
  });

  it("renders a static element for athlete name when contactsShown is false", () => {
    const wrapper = mount(ParticipantRow, {
      props: {
        row,
        canWrite: false,
        staff: false,
        contactsShown: false,
      },
    });

    const btn = wrapper.find("button[data-testid='participant-name']");
    expect(btn.exists()).toBe(false);

    const bold = wrapper.find("b[data-testid='participant-name']");
    expect(bold.exists()).toBe(true);
    expect(bold.text()).toBe("DUPONT Lucas");
  });
});
