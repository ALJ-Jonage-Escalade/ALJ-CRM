import { describe, expect, it } from "vitest";
import { member } from "./members.fixture";
import {
  attestationFileName,
  attestationProblem,
  attestationRecipient,
  attestationTemplates,
  changesOf,
  DEFAULT_ATTESTATION_TEMPLATE,
  draftOf,
  newMemberOf,
  recordRows,
  renderFor,
  signatureText,
  sameName,
  tarifChoices,
  withDateTag,
} from "./record";

describe("record", () => {
  it("lists the known fields only, with the payer when it is someone else", () => {
    const rows = recordRows(
      member({
        first_name: "Léa",
        last_name: "DUPONT",
        birth_date: "2012-05-04",
        age: 14,
        city: "Jonage",
        zip_code: "69330",
        payer: "Paul DUPONT",
        payer_email: "paul@example.org",
        amount: 180,
      }),
    );
    expect(rows.map((r) => `${r.label}=${r.value}`)).toEqual([
      "Date de naissance=04/05/2012 (14 ans)",
      "Adresse=69330 Jonage",
      "Payeur=Paul DUPONT (paul@example.org)",
      "Montant réglé=180 €",
    ]);
    expect(recordRows(member({ first_name: "Léa", last_name: "DUPONT", payer: "Léa DUPONT" }))).toEqual([]);
  });

  it("shows the key a member holds, linked to it on Outils › Clés", () => {
    const rows = recordRows(member({ key: { id: 4, code: "12", given_on: "2024-09-12" } }));
    expect(rows.find((r) => r.icon === "🔑")).toEqual({
      icon: "🔑",
      label: "Clé de la salle",
      value: "n° 12 depuis le 12/09/2024",
      to: "/bureau/outils/cles?cle=4",
    });
    expect(recordRows(member({ key: null })).find((r) => r.icon === "🔑")).toBeUndefined();
  });

  it("offers the slots' tariffs, the members' ones and the licence alone", () => {
    const choices = tarifChoices(
      [{ groupe: "Loisir adultes", tarifs: ["Adulte loisir"], categorie_age: "", type: "" }],
      [
        member({ tarif_name: "Ancien tarif" }),
        member({ tarif_name: "Adulte loisir", creneau_groupe: "Loisir adultes", creneau_details: "Lundi 19h" }),
      ],
    );
    expect(choices).toEqual([
      { tarif: "Adulte loisir", detail: "Loisir adultes" },
      { tarif: "Ancien tarif", detail: "" },
      { tarif: "Licence sèche", detail: "Licence seule · Sans créneau de cours" },
    ]);
  });
});

describe("edit and add", () => {
  it("sends only what changed, with a line per change", () => {
    const m = member({ phone: "06 12 34 56 78", badge_rouge: "x", status_norm: "Validé", commentaires_correctif: "" });
    expect(changesOf(m, draftOf(m))).toEqual({ fields: {}, lines: [] }); // "x" reads as Oui: no change
    const d = { ...draftOf(m), phone: "06 99 99 99 99", badge_rouge: "Non" as const, commentaires_correctif: "Certificat remis" };
    expect(changesOf(m, d)).toEqual({
      fields: { phone: "06 99 99 99 99", badge_rouge: "Non", commentaires_correctif: "Certificat remis" },
      lines: ["Badge rouge : Oui ➔ Non", "Téléphone : 06 12 34 56 78 ➔ 06 99 99 99 99", "Commentaire ajouté"],
    });
  });

  it("modifies identity, amount and emergency contacts when changed", () => {
    const m = member({
      last_name: "DUPONT",
      first_name: "Jean",
      birth_date: "2010-01-01",
      amount: 120,
      emergency1_name: "DUPONT Pierre",
      emergency1_phone: "06 01 02 03 04",
      photo_auth: "Oui",
    });
    const d = {
      ...draftOf(m),
      last_name: "martin",
      first_name: "Jeanne",
      birth_date: "2010-02-02",
      amount: "150.50",
      emergency1_name: "MARTIN Paul",
      emergency1_phone: "06 99 88 77 66",
      emergency2_name: "MARTIN Claire",
      emergency2_phone: "06 11 22 33 44",
      photo_auth: "Non" as const,
    };
    expect(changesOf(m, d)).toEqual({
      fields: {
        last_name: "MARTIN",
        first_name: "Jeanne",
        birth_date: "2010-02-02",
        amount: 150.5,
        emergency1_name: "MARTIN Paul",
        emergency1_phone: "06 99 88 77 66",
        emergency2_name: "MARTIN Claire",
        emergency2_phone: "06 11 22 33 44",
        photo_auth: "Non",
      },
      lines: [
        "Nom : DUPONT ➔ MARTIN",
        "Prénom : Jean ➔ Jeanne",
        "Date de naissance : 2010-01-01 ➔ 2010-02-02",
        "Droit à l'image : Oui ➔ Non",
        "Urgence 1 (nom) : DUPONT Pierre ➔ MARTIN Paul",
        "Urgence 1 (tél) : 06 01 02 03 04 ➔ 06 99 88 77 66",
        "Urgence 2 (nom) : vide ➔ MARTIN Claire",
        "Urgence 2 (tél) : vide ➔ 06 11 22 33 44",
        "Montant : 120 € ➔ 150.5 €",
      ],
    });
  });

  it("sends the sex as an FFME code, null to clear it", () => {
    const femaleMember = member({ sex: "F" });
    expect(changesOf(femaleMember, draftOf(femaleMember))).toEqual({ fields: {}, lines: [] });
    expect(changesOf(femaleMember, { ...draftOf(femaleMember), sex: "H" })).toEqual({
      fields: { sex: "H" },
      lines: ["Sexe : Femme ➔ Homme"],
    });
    expect(changesOf(femaleMember, { ...draftOf(femaleMember), sex: "" })).toEqual({
      fields: { sex: null },
      lines: ["Sexe : Femme ➔ Non renseigné"],
    });
  });

  it("never guesses the sex of a new member", () => {
    const draft = draftOf(undefined, "Adulte loisir");
    expect(draft.sex).toBe("");
    expect(newMemberOf(draft).sex).toBeNull();
    expect(newMemberOf({ ...draft, sex: "F" }).sex).toBe("F");
  });

  it("builds the new member: last name in capitals, French decimal amount", () => {
    const d = {
      ...draftOf(undefined, "Adulte loisir"),
      last_name: " dupont ",
      first_name: "Léa",
      birth_date: "2012-05-04",
      amount: "12,50",
    };
    expect(newMemberOf(d)).toEqual(
      expect.objectContaining({ last_name: "DUPONT", first_name: "Léa", amount: 12.5, tarif_name: "Adulte loisir", status: "Validé" }),
    );
  });

  it("finds a member of the same name, accents and case ignored", () => {
    const d = { ...draftOf(), last_name: "dupont", first_name: "lea" };
    expect(sameName([member({ last_name: "DUPONT", first_name: "Léa" })], d)).toBeDefined();
    expect(sameName([member({ last_name: "DUPONT", first_name: "Max" })], d)).toBeUndefined();
  });

  it("adds today's date on a new line of the comment", () => {
    const today = new Date(2026, 9, 22);
    expect(withDateTag("", today)).toBe("[22/10/2026] ");
    expect(withDateTag("Note", today)).toBe("Note\n[22/10/2026] ");
  });
});

describe("e-mail and certificate", () => {
  it("signs with the club's address from the server, or the name alone when it is unknown", () => {
    expect(signatureText("club@alj.example")).toBe("ALJ Escalade — Section de l'Amicale Laïque de Jonage\nclub@alj.example");
    expect(signatureText("")).toBe("ALJ Escalade — Section de l'Amicale Laïque de Jonage");
  });

  const m = member({ first_name: "LÉA-MARIE", last_name: "dupont", licence_ffme: "123456", amount: 180, season_name: "2026-2027" });

  it("replaces the variables, names case-insensitive, unknown ones kept", () => {
    expect(renderFor("{Prénom} {NOM} {num_licence} {montant} {saison} {inconnue}", m)).toBe(
      "Léa-Marie DUPONT 123456 180 € 2026-2027 {inconnue}",
    );
  });

  it("offers the default certificate template when the club has none named « échéance »", () => {
    expect(attestationTemplates([]).initial).toBe(DEFAULT_ATTESTATION_TEMPLATE);
    const own = { ...DEFAULT_ATTESTATION_TEMPLATE, name: "Attestation Échéance 2026" };
    expect(attestationTemplates([own])).toEqual({ list: [own], initial: own });
  });

  it("refuses cancelled or unpaid memberships, sends to the payer first", () => {
    expect(attestationProblem(m)).toBeNull();
    expect(attestationProblem(member({ amount: 0 }))).toBe("le montant est nul (0 €)");
    expect(attestationProblem(member({ amount: 50, status_norm: "Annulé" }))).toBe("la commande est annulée");
    expect(attestationRecipient(member({ payer_email: " p@x.org ", email_primary: "m@x.org" }))).toBe("p@x.org");
    expect(attestationRecipient(member({ email_primary: "m@x.org" }))).toBe("m@x.org");
    expect(attestationFileName(member({ last_name: "DE LA FONTAINE", first_name: "élodie" }))).toBe(
      "Attestation_DE_LA_FONTAINE_Elodie.pdf",
    );
  });
});
