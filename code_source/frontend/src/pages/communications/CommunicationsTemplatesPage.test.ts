import { fakeAuth, json, provided } from "../../test/harness";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type ApiFetch } from "../../lib/api";
import CommunicationsTemplatesPage from "./CommunicationsTemplatesPage.vue";
import { dialogs } from "../../composables/dialogs";

const RELANCE = {
  name: "Relance",
  subject: "Rappel {first_name}",
  body: "Bonjour",
  sender_email: "a@alj.example",
  sender_name: "ALJ",
  kind: "adherent",
};
const ECHEANCE = {
  name: "Rappel echeance",
  subject: "Échéance",
  body: "Payez",
  sender_email: "b@alj.example",
  sender_name: "ALJ",
  kind: "attestation",
};
const COUPE = {
  name: "Coupe",
  subject: "{name_competition}",
  body: "Lien : {whatapp_Id}",
  sender_email: "c@alj.example",
  sender_name: "ALJ",
  kind: "competition",
  needs_fixing: true,
};

/** The /api/email-templates answer: the templates and the club's sender settings. */
function templatesAnswer(templates: unknown[]): Response {
  return json({
    status: "success",
    templates,
    default_sender_email: "club@alj.example",
    default_sender_name: "Club",
    sender_suggestions: ["club@alj.example", "contact@alj.example"],
  });
}

type Answer = (body: unknown) => Response;
const ANSWERS: Record<string, Answer> = {
  "GET /api/email-templates": () => templatesAnswer([RELANCE, ECHEANCE]),
  "GET /api/whatsapp-template": () => json({ status: "success", template: "Rejoignez le groupe" }),
  "POST /api/email-templates": (body) => json({ status: "success", message: "ok", template: body }),
};

function render(answers: Record<string, Answer> = ANSWERS) {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const api: ApiFetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path: decodeURIComponent(u.pathname), body });
    const answer =
      answers[`${method} ${u.pathname}`] ?? (method === "DELETE" ? () => json({ status: "success", message: "ok" }) : undefined);
    return answer ? answer(body) : json({}, 404);
  });
  const auth = fakeAuth({ status: "signedIn", user: { uid: "u1", email: "admin@alj.example" }, role: "admin" });
  const wrapper = mount(CommunicationsTemplatesPage, {
    attachTo: document.body,
    global: {
      provide: provided(auth, api),
      stubs: { VersionBadge: true, PageLink: { template: "<a><slot /></a>" } },
    },
  });
  // The dialog is rendered at the end of <body>
  const byId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const value = (id: string) => (byId(id) as HTMLInputElement).value;
  const writes = () => calls.filter((c) => c.method !== "GET");
  return { wrapper, calls, writes, byId, value };
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("CommunicationsTemplatesPage", () => {
  it("opens the instalment reminder, with its preview and the WhatsApp text", async () => {
    const { byId, value } = render();
    await flushPromises();
    expect(value("template-select")).toBe("Rappel echeance");
    expect(value("template-name")).toBe("Rappel echeance");
    expect(value("subject")).toBe("Échéance");
    expect(byId("preview-from")!.textContent).toBe("ALJ <b@alj.example>");
    expect(value("whatsapp")).toBe("Rejoignez le groupe");
  });

  it("saves a renamed template under its former name, then shows it", async () => {
    const { wrapper, writes, byId } = render({
      ...ANSWERS,
      "GET /api/email-templates": () => templatesAnswer([{ ...RELANCE, name: "Relance 2" }, ECHEANCE]),
    });
    await flushPromises();
    await wrapper.find('[data-testid="template-select"]').setValue("Relance 2");
    await wrapper.find('[data-testid="template-name"]').setValue("Relance finale");
    await wrapper.find('[data-testid="subject"]').setValue("Dernier rappel {first_name}");
    expect(byId("preview-subject")!.textContent).toBe("Dernier rappel Alex");
    await wrapper.find('[data-testid="template-save"]').trigger("click");
    await flushPromises();
    expect(writes()).toEqual([
      {
        method: "POST",
        path: "/api/email-templates",
        body: { ...RELANCE, name: "Relance finale", subject: "Dernier rappel {first_name}", old_name: "Relance 2" },
      },
    ]);
    expect(byId("toast")!.textContent).toBe("💾 Modèle « Relance finale » enregistré avec succès !");
  });

  it("shows the variables as French labels and saves them as keys", async () => {
    const { wrapper, writes, value } = render({
      ...ANSWERS,
      "GET /api/email-templates": () =>
        templatesAnswer([{ ...RELANCE, kind: "competition", body: "Bonjour {first_name},\n{bloc_whatsapp}" }, ECHEANCE]),
    });
    await flushPromises();
    await wrapper.find('[data-testid="template-select"]').setValue("Relance");
    expect(value("subject")).toBe("Rappel {Prénom}");
    expect(value("body")).toBe("Bonjour {Prénom},\nVoici le lien du groupe WhatsApp dédié à cette compétition : {Lien WhatsApp}");
    await wrapper.find('[data-testid="body"]').setValue("Bonjour { PRENOM } {Nom de la compétition}");
    await wrapper.find('[data-testid="template-save"]').trigger("click");
    await flushPromises();
    expect(writes()[0]!.body).toMatchObject({ subject: "Rappel {first_name}", body: "Bonjour {first_name} {name_competition}" });
  });

  it("does not save a template with an unknown variable", async () => {
    const { wrapper, writes, byId } = render();
    await flushPromises();
    await wrapper.find('[data-testid="body"]').setValue("Bonjour {Prenon}");
    expect(byId("body-error")!.textContent).toContain("Variable inconnue : {Prenon}.");
    await wrapper.find("form").trigger("submit");
    expect(writes()).toEqual([]);
    expect(byId("toast")!.textContent).toContain("Variable inconnue : {Prenon}. Variables possibles : {Prénom}");
  });

  it("lists the templates by kind, those to fix marked", async () => {
    const { byId } = render({ ...ANSWERS, "GET /api/email-templates": () => templatesAnswer([COUPE, RELANCE, ECHEANCE]) });
    await flushPromises();
    const groups = [...byId("template-select")!.querySelectorAll("optgroup")].map((group) => [
      group.label,
      [...group.querySelectorAll("option")].map((option) => option.textContent.trim()),
    ]);
    expect(groups).toEqual([
      ["Adhérent", ["Relance"]],
      ["Attestation", ["Rappel echeance"]],
      ["Compétition", ["Coupe ⚠️ à corriger"]],
    ]);
  });

  it("offers the variables of the template's kind, and saves the kind chosen", async () => {
    const { wrapper, writes, byId } = render({ ...ANSWERS, "GET /api/email-templates": () => templatesAnswer([COUPE, RELANCE, ECHEANCE]) });
    await flushPromises();
    await wrapper.find('[data-testid="template-select"]').setValue("Coupe");
    expect(byId("template-needs-fixing")).not.toBeNull();
    expect((byId("body") as HTMLTextAreaElement).value).toBe("Lien : {Lien WhatsApp}");
    const offered = () => [...byId("body-variables")!.querySelectorAll("button")].map((b) => b.textContent.trim());
    expect(offered()).toContain("{Nom de la compétition}");
    expect(offered()).not.toContain("{Montant de l'adhésion}");

    await wrapper.find('[data-testid="template-kind"]').setValue("adherent");
    expect(offered()).not.toContain("{Nom de la compétition}");
    expect(byId("subject-error")!.textContent).toContain("Variable non disponible pour un modèle Adhérent : {Nom de la compétition}.");
    await wrapper.find("form").trigger("submit");
    expect(writes()).toEqual([]);

    await wrapper.find('[data-testid="template-kind"]').setValue("competition");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(writes()[0]!.body).toEqual({
      ...COUPE,
      needs_fixing: undefined,
      subject: "{name_competition}",
      body: "Lien : {whatsapp_link}",
      old_name: "Coupe",
    });
  });

  it("marks a template as its kind's default, and tells when a kind change drops the mark", async () => {
    const answers = { ...ANSWERS, "GET /api/email-templates": () => templatesAnswer([{ ...RELANCE, is_default: true }, ECHEANCE]) };
    const { wrapper, writes, byId } = render(answers);
    await flushPromises();
    const options = [...byId("template-select")!.querySelectorAll("option")].map((option) => option.textContent!.trim());
    expect(options).toEqual(["Relance ★ par défaut", "Rappel echeance"]);

    await wrapper.find('[data-testid="template-select"]').setValue("Relance");
    const box = () => byId("template-default") as HTMLInputElement;
    expect(box().checked).toBe(true);
    expect(byId("template-default-dropped")).toBeNull();
    await wrapper.find('[data-testid="template-kind"]').setValue("attestation");
    expect(box().checked).toBe(false);
    expect(byId("template-default-dropped")!.textContent).toContain("n'est plus le modèle par défaut");
    await wrapper.find('[data-testid="template-kind"]').setValue("adherent");
    expect(box().checked).toBe(true);

    await wrapper.find('[data-testid="template-select"]').setValue("Rappel echeance");
    await wrapper.find('[data-testid="template-default"]').setValue(true);
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(writes()[0]!.body).toMatchObject({ name: "Rappel echeance", kind: "attestation", is_default: true });
  });

  it("does not send an invalid template", async () => {
    const { wrapper, writes, byId } = render();
    await flushPromises();
    await wrapper.find('[data-testid="sender-email"]').setValue("pas-une-adresse");
    await wrapper.find("form").trigger("submit");
    expect(writes()).toEqual([]);
    expect(byId("toast")!.textContent).toBe("⚠️ L'adresse d'expédition doit être une adresse e-mail valide.");
  });

  it("shows the server's refusal", async () => {
    const { wrapper, byId } = render({
      ...ANSWERS,
      "POST /api/email-templates": () =>
        json({ status: "error", message: "Un modèle nommé « X » existe déjà.", code: "duplicate_name" }, 409),
    });
    await flushPromises();
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(byId("toast")!.textContent).toBe("❌ Erreur d'enregistrement : Un modèle nommé « X » existe déjà.");
  });

  it("creates a template from the dialog, and refuses an existing name", async () => {
    const { wrapper, writes, byId } = render();
    await flushPromises();
    await wrapper.find('[data-testid="template-new"]').trigger("click");
    await flushPromises();
    const name = byId("new-template-name") as HTMLInputElement;
    name.value = "relance";
    name.dispatchEvent(new Event("input"));
    byId("new-template-create")!.click();
    await flushPromises();
    expect(byId("toast")!.textContent).toBe("⚠️ Un modèle nommé « relance » existe déjà.");
    expect(writes()).toEqual([]);

    name.value = " Stage d'été ";
    name.dispatchEvent(new Event("input"));
    byId("new-template-create")!.click();
    await flushPromises();
    expect(writes()[0]!.body).toMatchObject({ name: "Stage d'été", subject: "Sujet du courriel", sender_email: "b@alj.example" });
    expect(byId("toast")!.textContent).toBe("➕ Nouveau modèle « Stage d'été » créé avec succès !");
    expect(byId("new-template-dialog")).toBeNull();
  });

  it("takes the sender suggestions and the default sender from the server", async () => {
    const { wrapper } = render();
    await flushPromises();
    const offered = wrapper.findAll('[data-testid="sender-suggestions"] option').map((option) => option.attributes("value"));
    expect(offered).toEqual(["club@alj.example", "contact@alj.example"]);
    await wrapper.find('[data-testid="sender-email"]').setValue("");
    await wrapper.find('[data-testid="sender-name"]').setValue("");
    expect(wrapper.find('[data-testid="sender-email"]').attributes("placeholder")).toBe("club@alj.example");
    expect(wrapper.find('[data-testid="preview-from"]').text()).toBe("Club <club@alj.example>");
  });

  it("deletes the template once confirmed", async () => {
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const { wrapper, writes, byId } = render();
    await flushPromises();
    await wrapper.find('[data-testid="template-delete"]').trigger("click");
    expect(writes()).toEqual([]);
    await wrapper.find('[data-testid="template-delete"]').trigger("click");
    await flushPromises();
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(writes()).toEqual([{ method: "DELETE", path: "/api/email-templates/Rappel echeance", body: undefined }]);
    expect(byId("toast")!.textContent).toBe("🗑️ Modèle « Rappel echeance » supprimé.");
  });

  it("saves the WhatsApp text, never empty", async () => {
    const { wrapper, writes, byId } = render({
      ...ANSWERS,
      "POST /api/whatsapp-template": () => json({ status: "success", message: "ok", template: "Nouveau" }),
    });
    await flushPromises();
    await wrapper.find('[data-testid="whatsapp"]').setValue("  ");
    await wrapper.find('[data-testid="whatsapp-save"]').trigger("click");
    expect(byId("toast")!.textContent).toBe("⚠️ Le texte WhatsApp ne peut pas être vide.");
    await wrapper.find('[data-testid="whatsapp"]').setValue("Nouveau");
    await wrapper.find('[data-testid="whatsapp-save"]').trigger("click");
    await flushPromises();
    expect(writes()).toEqual([{ method: "POST", path: "/api/whatsapp-template", body: { template: "Nouveau" } }]);
    expect(byId("toast")!.textContent).toBe("💾 Texte WhatsApp enregistré avec succès !");
  });

  it("says when there is no template yet", async () => {
    const { wrapper, byId } = render({ ...ANSWERS, "GET /api/email-templates": () => templatesAnswer([]) });
    await flushPromises();
    expect(wrapper.text()).toContain("Aucun modèle pour l'instant");
    expect(byId("template-name")).toBeNull();
    expect(byId("template-delete")!.hasAttribute("disabled")).toBe(true);
  });
});
