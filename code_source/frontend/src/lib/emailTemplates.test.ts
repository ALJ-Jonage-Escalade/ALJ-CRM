import { describe, expect, it } from "vitest";
import type { EmailTemplate } from "../services/communications";
import { initialOfKind, senderFields, templatesOfKind } from "./emailTemplates";

const t = (name: string, kind: EmailTemplate["kind"], is_default = false): EmailTemplate => ({
  name,
  kind,
  is_default,
  subject: "",
  body: "",
  sender_email: "",
  sender_name: "",
});
const TEMPLATES = [
  t("Bienvenue", "adherent"),
  t("Coupe", "competition"),
  t("Relance", "competition", true),
  t("Attestation", "attestation"),
];

describe("sender of a send request", () => {
  it("is the template's when one is used, else the address chosen", () => {
    expect(senderFields(t("Relance", "adherent"), "b@x.fr")).toEqual({ template_name: "Relance" });
    expect(senderFields(undefined, "b@x.fr")).toEqual({ sender_email: "b@x.fr" });
    expect(senderFields(undefined, "")).toEqual({ sender_email: "" }); // the sending account
  });
});

describe("templates of a screen", () => {
  it("keeps the templates of the kind", () => {
    expect(templatesOfKind(TEMPLATES, "competition").map((template) => template.name)).toEqual(["Coupe", "Relance"]);
  });

  it("opens the kind's default, else the screen's rule", () => {
    const firstOne = (list: readonly EmailTemplate[]) => list[0];
    expect(initialOfKind(TEMPLATES, "competition", firstOne)?.name).toBe("Relance");
    expect(initialOfKind(TEMPLATES, "adherent", firstOne)?.name).toBe("Bienvenue");
    expect(initialOfKind(TEMPLATES, "adherent", () => undefined)).toBeUndefined();
  });
});
