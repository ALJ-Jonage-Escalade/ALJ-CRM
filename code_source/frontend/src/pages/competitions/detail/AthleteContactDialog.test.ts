import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import AthleteContactDialog from "./AthleteContactDialog.vue";
import type { Row } from "../competitions";

describe("AthleteContactDialog", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  const athlete: Row = {
    adherent_id: 12,
    nom: "DUPONT",
    prenom: "Lucas",
    num_licence: "654321",
    tarif: "Compétition U18",
    group: "Compétition U18",
    categorie_ffme: "U18",
    selectionne: true,
    present: false,
    statut_paiement: "paye",
    montant_paye: 15,
    commande_helloasso: "",
    note_paiement: "",
    urgence_nom: "",
    urgence_tel: "",
    phone: "06 00 11 22 33",
    email: "lucas@test.fr",
    emergency: [],
    queued: { selectionne: false, present: false },
    contacts: [
      {
        role: "athlete",
        title: "🧗 Athlète",
        name: "Lucas DUPONT",
        phone: "06 00 11 22 33",
        email: "lucas@test.fr",
      },
      {
        role: "emergency1",
        title: "🚨 Contact d'urgence 1",
        name: "Marie Dupont",
        phone: "06 11 11 11 11",
        email: "marie@test.fr",
      },
      {
        role: "emergency2",
        title: "🚨 Contact d'urgence 2",
        name: "Jean Dupont",
        phone: "06 22 22 22 22",
        email: "",
      },
    ],
  };

  it("renders the 3 contact cards with details and links", async () => {
    const wrapper = mount(AthleteContactDialog, {
      attachTo: document.body,
      props: {
        athlete,
        open: true,
      },
    });
    await flushPromises();

    const dialog = document.body.querySelector("[data-testid='athlete-contact-dialog']");
    expect(dialog).not.toBeNull();

    const cards = document.body.querySelectorAll("[data-testid='contact-card']");
    expect(cards).toHaveLength(3);

    // Card 1: Athlète
    expect(cards[0]!.querySelector("[data-testid='contact-title']")?.textContent).toBe("🧗 Athlète");
    expect(cards[0]!.querySelector("[data-testid='contact-name']")?.textContent).toBe("Lucas DUPONT");
    expect(cards[0]!.querySelector("[data-testid='contact-phone-link']")?.getAttribute("href")).toBe("tel:0600112233");
    expect(cards[0]!.querySelector("[data-testid='contact-email-link']")?.getAttribute("href")).toBe("mailto:lucas@test.fr");

    // Card 2: Urgence 1
    expect(cards[1]!.querySelector("[data-testid='contact-title']")?.textContent).toBe("🚨 Contact d'urgence 1");
    expect(cards[1]!.querySelector("[data-testid='contact-name']")?.textContent).toBe("Marie Dupont");
    expect(cards[1]!.querySelector("[data-testid='contact-phone-link']")?.getAttribute("href")).toBe("tel:0611111111");
    expect(cards[1]!.querySelector("[data-testid='contact-email-link']")?.getAttribute("href")).toBe("mailto:marie@test.fr");

    // Card 3: Urgence 2 (no email)
    expect(cards[2]!.querySelector("[data-testid='contact-title']")?.textContent).toBe("🚨 Contact d'urgence 2");
    expect(cards[2]!.querySelector("[data-testid='contact-name']")?.textContent).toBe("Jean Dupont");
    expect(cards[2]!.querySelector("[data-testid='contact-phone-link']")?.getAttribute("href")).toBe("tel:0622222222");
    expect(cards[2]!.querySelector("[data-testid='contact-email-link']")).toBeNull();

    wrapper.unmount();
  });

  it("emits update:open false when closing", async () => {
    const wrapper = mount(AthleteContactDialog, {
      attachTo: document.body,
      props: {
        athlete,
        open: true,
      },
    });
    await flushPromises();

    const closeBtn = document.body.querySelector("[data-testid='close-contact-dialog']") as HTMLButtonElement;
    expect(closeBtn).not.toBeNull();
    closeBtn.click();
    await flushPromises();

    expect(wrapper.emitted("update:open")).toEqual([[false]]);
    wrapper.unmount();
  });
});
