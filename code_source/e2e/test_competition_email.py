"""E-mail to the competitors of a competition: sent by the server, captured by Mailpit."""
import re

import pytest
from playwright.sync_api import expect

from helpers.competitions import open_competition, open_screen, toast
from helpers.data import unique_name
from helpers.dialogs import accept_dialogs


@pytest.fixture
def competition(test_data):
    """Two selected competitors with an e-mail address, one invited only."""
    members = [m for m in test_data.competition_group() if "@" in (m.get("email") or "")][:3]
    assert len(members) == 3, "the seed gives most members an e-mail address"
    nom = unique_name("E2E Mail")
    test_data.create_competition(nom, date="2027-09-18", prix=9, participants=[m["id"] for m in members],
                                 selected=[m["id"] for m in members[:2]])
    return {"nom": nom, "selected": members[:2], "invited": members[2]}


def _assert_sent_to_selected(mailpit, competition):
    sent = mailpit.wait_for(f'subject:"{competition["nom"]}"', count=2)
    recipients = sorted(m["To"][0]["Address"] for m in sent)
    assert recipients == sorted(m["email"].lower() for m in competition["selected"])
    assert all(competition["nom"] in m["Subject"] for m in sent), "competition variables resolved by the server"
    assert not mailpit.messages(f'to:{competition["invited"]["email"]} subject:"{competition["nom"]}"')


def test_mobile_campaign(mobile_page, mailpit, competition):
    page = open_screen(mobile_page)
    accept_dialogs(page)
    open_competition(page, competition["nom"])
    # In the « Plus » menu on a phone, not next to « Modifier »
    expect(page.get_by_test_id("detail-actions").get_by_test_id("email-comp")).to_have_count(0)
    page.get_by_test_id("detail-more").click()
    page.get_by_test_id("email-comp").click()
    expect(page.get_by_test_id("email-dialog")).to_be_visible()
    expect(page.get_by_test_id("email-count")).to_have_text("2 destinataires avec une adresse e-mail")
    # Pre-filled from the seeded « Competition call-up » template, previewed for the first recipient
    expect(page.get_by_test_id("email-subject")).to_have_value(re.compile(r"\{Nom de la compétition\}"))
    expect(page.get_by_test_id("email-preview")).to_contain_text(competition["nom"])
    page.get_by_test_id("email-send").click()
    expect(toast(page)).to_contain_text("2 e-mail(s) envoyé(s)")
    expect(page.get_by_test_id("email-dialog")).to_be_hidden()
    _assert_sent_to_selected(mailpit, competition)


def test_desktop_campaign(page, mailpit, competition):
    open_screen(page, "admin", "/bureau/competitions")
    accept_dialogs(page)
    open_competition(page, competition["nom"])
    page.get_by_test_id("email-comp").click()
    page.get_by_test_id("email-audience-all").check()
    expect(page.get_by_test_id("email-count")).to_have_text("3 destinataires avec une adresse e-mail")
    page.get_by_test_id("email-audience-selected").check()
    # The default template fills the body once loaded; sending before that is refused (empty message)
    expect(page.get_by_test_id("email-body")).not_to_have_value("")
    page.get_by_test_id("email-subject").fill("Convocation {name_competition}")
    page.get_by_test_id("email-send").click()
    expect(toast(page)).to_contain_text("envoyé(s) avec succès")
    _assert_sent_to_selected(mailpit, competition)
