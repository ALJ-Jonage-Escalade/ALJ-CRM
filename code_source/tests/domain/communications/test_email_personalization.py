"""Filling a template from a member and a competition (domain/communications/email_personalization.py)."""

from __future__ import annotations

import pytest

from domain.communications.email_personalization import apply_template_variables

MEMBER = {"first_name": "camille", "last_name": "durand", "licence_ffme": "654321", "tarif_name": "Jeunes 2010",
          "season_name": "2026-2027", "amount": 195.5}
COMPETITION = {"name_competition": "Coupe du Rhône", "no_competition": "2026-42", "date_competition": "15/11/2026",
               "montant_competition": "15", "whatsapp_link": "https://chat.whatsapp.com/abc"}


@pytest.mark.parametrize(("amount", "expected"), [(195.5, "195,50"), (15, "15"), ("15.00", "15"), (None, "")])
def test_amount_uses_the_french_format_without_currency(amount: object, expected: str) -> None:
    assert apply_template_variables("[{amount}]", {**MEMBER, "amount": amount}) == f"[{expected}]"


def test_fills_member_and_competition_variables_with_former_spellings() -> None:
    text = "{prenom} {Nom} ({num_licence}, {tarif}, {season}) : {nom_competition} n°{no_competition} le {date_competition}, {montant_competition} €\n{bloc_whatsapp}"
    assert apply_template_variables(text, MEMBER, COMPETITION) == (
        "Camille DURAND (654321, Jeunes 2010, 2026-2027) : Coupe du Rhône n°2026-42 le 15/11/2026, 15 €\n"
        "Voici le lien du groupe WhatsApp dédié à cette compétition : https://chat.whatsapp.com/abc"
    )


def test_a_member_e_mail_leaves_no_competition_token() -> None:
    text = "Bonjour {first_name},\nCompétition : {name_competition}\nGroupe : {whatsapp_link}\nFin"
    assert apply_template_variables(text, {"first_name": "léa"}) == "Bonjour Léa,\nCompétition : \nFin"
