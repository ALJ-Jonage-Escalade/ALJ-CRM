import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { AUTH_KEY, type Auth } from "../composables/auth";
import { API_KEY, type ApiFetch } from "../lib/api";
import { CLIENT_KEY, createApiClient } from "../lib/client";
import CommunicationsPage from "./CommunicationsPage.vue";
import { dialogs } from "../composables/dialogs";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const RELANCE = { name: "Relance", subject: "Rappel {first_name}", body: "Bonjour", sender_email: "a@alj.example", sender_name: "ALJ" };
const ECHEANCE = { name: "Rappel echeance", subject: "Échéance", body: "Payez", sender_email: "b@alj.example", sender_name: "ALJ" };

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
  const auth: Auth = {
    state: ref({ status: "signedIn", user: { uid: "u1", email: "admin@alj.example" }, role: "admin" }),
    login: vi.fn(),
    logout: vi.fn(async () => {}),
    retry: vi.fn(async () => {}),
    stop: vi.fn(),
  };
  const wrapper = mount(CommunicationsPage, {
    attachTo: document.body,
    global: {
      provide: { [AUTH_KEY]: auth, [API_KEY]: api, [CLIENT_KEY]: createApiClient(api, "http://alj.test") },
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

describe("CommunicationsPage", () => {
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
