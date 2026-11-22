import { json } from "../../../test/harness";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { dialogs } from "../../../composables/dialogs";
import type { ApiFetch } from "../../../lib/api";
import { CLIENT_KEY, createApiClient } from "../../../lib/client";
import EmailForm from "./EmailForm.vue";
import { participantRows, type Competition } from "../competitions";

const COMP: Competition = {
  id: 10,
  nom: "Coupe",
  participants: [{ adherent_id: 1, nom: "Martin", prenom: "Léo", selectionne: true, email: "leo@x.fr" }],
};
const TEMPLATE = {
  name: "Compétition - 1er Inscription",
  subject: "Inscription {name_competition}",
  body: "Bonjour",
  sender_email: "",
  sender_name: "",
  kind: "competition",
};
const RELANCE = { ...TEMPLATE, name: "Relance", subject: "Relance {first_name}", body: "Lien : {whatapp_Id}", is_default: true };
const ADHERENT = { ...TEMPLATE, name: "Compétition jeunes (adhérents)", kind: "adherent", is_default: true };

/** The form, with the templates answer held back until release() is called. */
function mountForm(templates: unknown[] = [TEMPLATE]) {
  const sent: unknown[] = [];
  let release = (): void => undefined;
  const templatesAnswered = new Promise<void>((resolve) => (release = resolve));
  const api: ApiFetch = async (url, init) => {
    if (url.endsWith("/api/email-templates")) {
      await templatesAnswered;
      return json({ status: "success", templates });
    }
    if (url.endsWith("/api/send-email")) {
      sent.push(JSON.parse(init?.body as string));
      return json({ status: "success", sent_count: 1, errors_count: 0, total_recipients: 1, details: [] });
    }
    return json({ status: "success", configured: true, mode: "smtp", sender: "club@x.fr" });
  };
  const wrapper = mount(EmailForm, {
    props: { competition: COMP, rows: participantRows(COMP, [], []) },
    global: { provide: { [CLIENT_KEY]: createApiClient(api, "http://alj.test") } },
  });
  const field = (id: string) => wrapper.find<HTMLInputElement | HTMLTextAreaElement>(`[data-testid="${id}"]`).element;
  return { wrapper, field, release, sent };
}

describe("competition e-mail form", () => {
  it("fills in the default template once loaded", async () => {
    const { field, release } = mountForm();
    release();
    await flushPromises();
    expect(field("email-subject").value).toBe("Inscription {Nom de la compétition}");
    expect(field("email-body").value).toBe(TEMPLATE.body);
  });

  it("offers the competition templates only, the default one first, written with labels", async () => {
    const { wrapper, field, release } = mountForm([TEMPLATE, ADHERENT, RELANCE]);
    release();
    await flushPromises();
    const offered = wrapper.findAll('[data-testid="email-template"] option').map((option) => option.text());
    expect(offered).toEqual(["— Saisie libre —", "Compétition - 1er Inscription", "Relance"]);
    expect(field("email-subject").value).toBe("Relance {Prénom}");
    expect(field("email-body").value).toBe("Lien : {Lien WhatsApp}");
  });

  it("offers the competition variables for a free text, and sends their keys", async () => {
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    const { wrapper, release, sent } = mountForm();
    release();
    await flushPromises();
    await wrapper.find('[data-testid="email-template"]').setValue("");
    await wrapper.find('[data-testid="email-subject"]').setValue("{Nom de la compétition}");
    await wrapper.find('[data-testid="email-body"]').setValue("Bonjour { prénom }, rendez-vous le {Date de la compétition}");
    const labels = wrapper.findAll('[data-testid="email-body-variables"] button').map((b) => b.text());
    expect(labels).toContain("{Nom de la compétition}");
    expect(labels).not.toContain("{Montant de l'adhésion}");
    expect(wrapper.find('[data-testid="email-preview"]').text()).toContain("Sujet : Coupe");

    await wrapper.find('[data-testid="email-body"]').setValue("Bonjour {Prenon}");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(sent).toEqual([]);
    expect(wrapper.find('[data-testid="email-problem"]').text()).toContain("Variable inconnue : {Prenon}.");

    await wrapper.find('[data-testid="email-body"]').setValue("Bonjour { prénom }, rendez-vous le {Date de la compétition}");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(sent).toEqual([
      expect.objectContaining({ subject: "{name_competition}", body: "Bonjour {first_name}, rendez-vous le {date_competition}" }),
    ]);
  });

  it("keeps what the user wrote before the templates arrived", async () => {
    const { wrapper, field, release } = mountForm();
    await wrapper.find('[data-testid="email-subject"]').setValue("Convocation");
    release();
    await flushPromises();
    expect(field("email-subject").value).toBe("Convocation");
    expect(field("email-body").value).toBe("");
  });
});
