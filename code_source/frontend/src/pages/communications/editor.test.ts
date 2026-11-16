import type { EmailTemplate } from "../../services/communications";
import { fillTemplate } from "../../lib/text";
import { describe, expect, it } from "vitest";
import {
  initialTemplate,
  insertText,
  linkTags,
  linkTarget,
  newNameError,
  newTemplate,
  preview,
  DEMO_VALUES,
  templateError,
  VARIABLES,
  wrapSelection,
} from "./editor";

const TEMPLATE: EmailTemplate = {
  name: "Relance",
  subject: "Licence {num_licence}",
  body: "Bonjour {first_name}",
  sender_email: "competitions@alj-escalade.fr",
  sender_name: "ALJ Compétitions",
};
const CLUB_SENDER = { sender_email: "inscription@alj-escalade.fr", sender_name: "Amicale Laïque Jonage - Inscriptions" };

describe("preview", () => {
  it("renders the variables with the demo member", () => {
    expect(preview(TEMPLATE, CLUB_SENDER)).toEqual({
      from: "ALJ Compétitions <competitions@alj-escalade.fr>",
      subject: "Licence 847291",
      body: "Bonjour Alex",
    });
  });

  it("ignores the case of variable names and keeps unknown ones", () => {
    expect(fillTemplate("{FIRST_NAME} {Nom} {Prénom} {inconnue} {season}", DEMO_VALUES)).toBe("Alex MARTIN Alex {inconnue} 2026-2027");
  });

  it("falls back to the club's sender and placeholders", () => {
    expect(preview({ ...TEMPLATE, subject: "", body: "", sender_email: " ", sender_name: "" }, CLUB_SENDER)).toEqual({
      from: "Amicale Laïque Jonage - Inscriptions <inscription@alj-escalade.fr>",
      subject: "(Sans objet)",
      body: "(Message vide)",
    });
  });

  it("offers every variable of the demo member", () => {
    expect(VARIABLES).toContain("{montant_competition}");
    expect(VARIABLES).toContain("{competition_deadline}");
    for (const v of VARIABLES) {
      expect(fillTemplate(v, DEMO_VALUES)).not.toBe(v);
    }
  });
});

describe("templateError", () => {
  it.each([
    [{}, null],
    [{ name: " " }, "⚠️ Le titre du modèle ne peut pas être vide."],
    [{ subject: "" }, "⚠️ Le sujet et le corps du message sont obligatoires."],
    [{ body: "  " }, "⚠️ Le sujet et le corps du message sont obligatoires."],
    [{ sender_email: "" }, "⚠️ L'adresse d'expédition doit être une adresse e-mail valide."],
    [{ sender_email: "pas-une-adresse" }, "⚠️ L'adresse d'expédition doit être une adresse e-mail valide."],
  ])("%j", (change, message) => {
    expect(templateError({ ...TEMPLATE, ...change })).toBe(message);
  });
});

describe("new templates", () => {
  it("refuses an empty or existing name (case ignored)", () => {
    expect(newNameError("", [TEMPLATE])).toBe("⚠️ Veuillez renseigner le nom du modèle.");
    expect(newNameError("RELANCE", [TEMPLATE])).toBe("⚠️ Un modèle nommé « RELANCE » existe déjà.");
    expect(newNameError("Stage", [TEMPLATE])).toBeNull();
  });

  it("start from the sender being edited", () => {
    expect(newTemplate("Stage", TEMPLATE)).toMatchObject({
      name: "Stage",
      subject: "Sujet du courriel",
      sender_email: "competitions@alj-escalade.fr",
    });
    // Empty sender: left to the server, which puts the club's default
    expect(newTemplate("Stage", { sender_email: " ", sender_name: "" })).toMatchObject({ sender_email: "", sender_name: "" });
  });

  it("show the requested template, else the instalment reminder, else the first", () => {
    const echeance = { ...TEMPLATE, name: "Rappel echeance" };
    expect(initialTemplate([TEMPLATE, echeance], "Relance")).toBe(TEMPLATE);
    expect(initialTemplate([TEMPLATE, echeance], "Supprimé")).toBe(echeance);
    expect(initialTemplate([TEMPLATE])).toBe(TEMPLATE);
    expect(initialTemplate([])).toBeUndefined();
  });
});

describe("body edits", () => {
  it("insert a variable in place of the selection", () => {
    expect(insertText("Bonjour X !", 8, 9, "{first_name}")).toEqual({ value: "Bonjour {first_name} !", start: 20, end: 20 });
  });

  it("wrap the selection, or a placeholder", () => {
    expect(wrapSelection("un mot ici", 3, 6, "<b>", "</b>")).toEqual({ value: "un <b>mot</b> ici", start: 6, end: 9 });
    expect(wrapSelection("", 0, 0, "<i>", "</i>")).toEqual({ value: "<i>texte</i>", start: 3, end: 8 });
  });

  it("make links from the prompt's answer", () => {
    expect(linkTarget(null)).toBeNull();
    expect(linkTarget("https://")).toBeNull();
    expect(linkTarget(" https://www.alj-escalade.fr ")).toBe("https://www.alj-escalade.fr");
    expect(linkTags('https://x.fr/?a=1&b="2"')).toEqual(['<a href="https://x.fr/?a=1&amp;b=&quot;2&quot;">', "</a>"]);
  });
});
