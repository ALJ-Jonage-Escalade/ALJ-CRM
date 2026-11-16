import { json } from "../../../test/harness";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
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
};

/** The form, with the templates answer held back until release() is called. */
function mountForm() {
  let release = (): void => undefined;
  const templatesAnswered = new Promise<void>((resolve) => (release = resolve));
  const api: ApiFetch = async (url) => {
    if (url.endsWith("/api/email-templates")) {
      await templatesAnswered;
      return json({ status: "success", templates: [TEMPLATE] });
    }
    return json({ status: "success", configured: true, mode: "smtp", sender: "club@x.fr" });
  };
  const wrapper = mount(EmailForm, {
    props: { competition: COMP, rows: participantRows(COMP, [], []) },
    global: { provide: { [CLIENT_KEY]: createApiClient(api, "http://alj.test") } },
  });
  const field = (id: string) => wrapper.find<HTMLInputElement | HTMLTextAreaElement>(`[data-testid="${id}"]`).element;
  return { wrapper, field, release };
}

describe("competition e-mail form", () => {
  it("fills in the default template once loaded", async () => {
    const { field, release } = mountForm();
    release();
    await flushPromises();
    expect(field("email-subject").value).toBe(TEMPLATE.subject);
    expect(field("email-body").value).toBe(TEMPLATE.body);
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
