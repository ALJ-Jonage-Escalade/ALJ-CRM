import { describe, expect, it } from "vitest";
import { participantRows, type Competition } from "../competitions";
import { amountText, audience, defaultTemplate, render, sendBody, variables } from "./email";

const COMP: Competition = {
  id: 10,
  nom: "Coupe",
  id_ffme: "EVT-9",
  prix: 15.5,
  date_competition: "2027-03-14",
  date_fin: "2027-03-15",
  whatsapp_link: "https://chat",
  participants: [
    { adherent_id: 1, nom: "Martin", prenom: "Léo", selectionne: true, statut_paiement: "paye", email: "leo@x.fr", num_licence: "123" },
    { adherent_id: 2, nom: "Durand", prenom: "Zoé", selectionne: true, statut_paiement: "en_attente", email: "" },
    { adherent_id: 3, nom: "Abel", prenom: "Max", selectionne: false, email: "max@x.fr" },
    { adherent_id: null, nom: "Inconnu", selectionne: true },
  ],
};
const ROWS = participantRows(COMP, [{ id: 2, email: "", email_secondaire: "zoe@x.fr" }], []);

describe("competition e-mail", () => {
  it("picks the audience among the known members", () => {
    expect(audience(ROWS, "selected").map((r) => r.adherent_id)).toEqual([1, 2]);
    expect(audience(ROWS, "unpaid").map((r) => r.adherent_id)).toEqual([2]);
    expect(audience(ROWS, "all").map((r) => r.adherent_id)).toEqual([1, 2, 3]);
  });

  it("fills the competition's variables as the server does", () => {
    const values = variables(COMP, ROWS[0]);
    expect(
      render(
        "{First_Name} {last_name} : {name_competition} n°{no_competition} du {date_competition}, {montant_competition} €. {bloc_whatsapp} {inconnu}",
        values,
      ),
    ).toBe(
      "Léo MARTIN : Coupe n°EVT-9 du 14/03/2027 au 15/03/2027, 15,50 €. Voici le lien du groupe WhatApp dédié à cette compétition : https://chat {inconnu}",
    );
    expect([amountText(15), amountText(15.5), amountText(null)]).toEqual(["15", "15,50", ""]);
    expect(variables({ ...COMP, date_fin: "2027-03-14" }, undefined).date_competition).toBe("14/03/2027");
  });

  it("offers the club's competition template first", () => {
    const t = (name: string) => ({ name, subject: "", body: "", sender_email: "", sender_name: "" });
    expect(defaultTemplate([t("Bienvenue"), t("Compétition - relance"), t("Compétition - 1er Inscription")])!.name).toBe(
      "Compétition - 1er Inscription",
    );
    expect(defaultTemplate([t("Bienvenue"), t("Competition call-up")])!.name).toBe("Competition call-up");
    expect(defaultTemplate([t("Bienvenue")])!.name).toBe("Bienvenue");
    expect(defaultTemplate([])).toBeUndefined();
  });

  it("sends to the recipients with an address, the secondary one when needed", () => {
    const body = sendBody(COMP, audience(ROWS, "selected"), " Sujet ", "Texte ");
    expect(body).toEqual({
      subject: "Sujet",
      body: "Texte",
      competition_id: 10,
      recipients: [
        { id: 1, first_name: "Léo", last_name: "Martin", email: "leo@x.fr", num_licence: "123" },
        { id: 2, first_name: "Zoé", last_name: "Durand", email: "zoe@x.fr", num_licence: "" },
      ],
    });
  });
});
