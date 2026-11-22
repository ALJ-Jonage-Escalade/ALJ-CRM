"""The e-mail template variables (domain/email_variables.py): rendering, aliases, empty values."""

from __future__ import annotations

import pytest

from domain.email_variables import render_template, template_error, to_keys, to_labels


def test_render_template_fills_each_variable() -> None:
    assert render_template("Bonjour {first_name} {last_name}", {"first_name": "Alex", "last_name": "MARTIN"}) == "Bonjour Alex MARTIN"


@pytest.mark.parametrize("token", ["{Prénom}", "{prénom}", "{PRENOM}", "{ Prénom }", "{first_name}", "{First_Name}"])
def test_render_template_matches_leniently(token: str) -> None:
    assert render_template(f"Bonjour {token} !", {"first_name": "Alex"}) == "Bonjour Alex !"


@pytest.mark.parametrize(("alias", "key"), [
    ("{nom_competition}", "name_competition"),
    ("{whatapp_Id}", "whatsapp_link"),
    ("{whatsapp_id}", "whatsapp_link"),
    ("{whatapp_link}", "whatsapp_link"),
    ("{prenom}", "first_name"),
    ("{Nom}", "last_name"),
])
def test_render_template_accepts_former_spellings(alias: str, key: str) -> None:
    assert render_template(f"[{alias}]", {key: "valeur"}) == "[valeur]"


def test_render_template_expands_the_former_whatsapp_block() -> None:
    rendered = render_template("Infos :\n{bloc_whatsapp}\nÀ bientôt", {"whatsapp_link": "https://chat.whatsapp.com/abc"})
    assert rendered == "Infos :\nVoici le lien du groupe WhatsApp dédié à cette compétition : https://chat.whatsapp.com/abc\nÀ bientôt"


def test_render_template_leaves_nothing_for_an_empty_value() -> None:
    assert render_template("Groupe {tarif}, saison {season}.", {"tarif": "", "season": "  "}) == "Groupe , saison ."


@pytest.mark.parametrize("token", ["{whatsapp_link}", "{Lien WhatsApp}", "{bloc_whatsapp}"])
def test_render_template_removes_the_line_of_an_empty_whatsapp_link(token: str) -> None:
    text = f"Bonjour,\n\nLe groupe : {token}\n\nÀ bientôt"
    assert render_template(text, {"whatsapp_link": ""}) == "Bonjour,\n\nÀ bientôt"


def test_render_template_escapes_values_for_html() -> None:
    rendered = render_template("<b>{first_name}</b>", {"first_name": '<a href="x">R&D</a>'}, escape_html=True)
    assert rendered == "<b>&lt;a href=&quot;x&quot;&gt;R&amp;D&lt;/a&gt;</b>"


def test_render_template_leaves_braces_of_html_and_unknown_tokens() -> None:
    text = '{<b>Prénom</b>} {style="a"} {inconnu} {Prénom\n}'
    assert render_template(text, {"first_name": "Alex"}) == text


def test_to_keys_stores_lenient_labels_and_former_spellings_as_keys() -> None:
    text = "Bonjour { prénom } {NOM}, {nom_competition} : {Lien WhatsApp}\n{bloc_whatsapp} {inconnu} <a href=\"x\">{N° de licence}</a>"
    assert to_keys(text) == (
        "Bonjour {first_name} {last_name}, {name_competition} : {whatsapp_link}\n"
        "Voici le lien du groupe WhatsApp dédié à cette compétition : {whatsapp_link} {inconnu} <a href=\"x\">{num_licence}</a>"
    )


def test_to_labels_shows_keys_and_former_spellings_as_labels() -> None:
    assert to_labels("{first_name} {Prénom} {whatapp_Id} {amount} {inconnu}") == "{Prénom} {Prénom} {Lien WhatsApp} {Montant de l'adhésion} {inconnu}"


def test_labels_and_keys_round_trip() -> None:
    stored = "Bonjour {first_name} {last_name} ({num_licence}, {tarif}, {season}, {amount}) {name_competition} {whatsapp_link}"
    assert to_keys(to_labels(stored)) == stored


def test_template_error_names_unknown_tokens_and_lists_the_valid_labels() -> None:
    message = template_error(["Bonjour {Prenon}", "{ prénom } {bloc_whatsapp} {Prenon} {date limite}"])
    assert message is not None
    assert message.startswith("Variables inconnues : {Prenon}, {date limite}.")
    assert "{Prénom}" in message and "{Lien WhatsApp}" in message


def test_template_error_accepts_known_tokens_and_html() -> None:
    assert template_error(['{PRENOM} {nom_competition} <a href="https://x.fr">{style="a"}</a>']) is None
