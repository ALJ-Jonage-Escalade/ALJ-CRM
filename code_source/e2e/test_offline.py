"""Competitions screen without network (plan D2, phase 11): the last data received is kept in IndexedDB
(frontend/src/lib/store.ts). Competitors' emergency contacts are kept for coaches only, and the store is wiped on
logout. Offline, only « Participe » and « Présent » change: kept in the outbox (pages/competitions/outbox.ts) and
sent when the network comes back, refused if the participant changed meanwhile. What the former phone page queued
is sent too. Logging out with changes not sent asks first.

Service workers are blocked in the e2e contexts, so "offline" is simulated by making every API call fail
while the page itself still loads."""
import pytest
from playwright.sync_api import expect

from helpers.competitions import open_competition, open_screen, participant_card, toast
from helpers.data import eventually, unique_name
from helpers.offline import owner, put_queued, queued, stored, wait_stored


@pytest.fixture
def competition(test_data):
    member = test_data.members(competition_only=True)[0]
    nom = unique_name("E2E Offline")
    cid = test_data.create_competition(nom, date="2027-12-04", participants=[member["id"]], selected=[member["id"]])
    return {"id": cid, "nom": nom, "member": member}


def emergency_links(page, member):
    return participant_card(page, member).get_by_test_id("emergency-link")


def go_offline(page, context, competition) -> None:
    """Page restarted from the store with the API unreachable, then the network cut. The competition is open: on a
    phone its detail replaces the list."""
    # Up to one poll (20 s): the server caches the competition list for 5 s
    wait_stored(page, "competitions", lambda data: any(c["id"] == competition["id"] for c in data), timeout=30)
    wait_stored(page, "competitors")
    context.route("**/api/**", lambda route: route.abort("internetdisconnected"))
    page.reload()
    expect(page.get_by_test_id("detail-name")).to_have_text(competition["nom"])
    context.set_offline(True)
    expect(page.locator("#sync-info")).to_contain_text("Hors ligne")


def go_online(page, context) -> None:
    context.unroute("**/api/**")
    context.set_offline(False)
    page.evaluate("() => window.dispatchEvent(new Event('online'))")


def participant(test_data, competition) -> dict:
    doc = test_data.competition(competition["id"])
    return next(p for p in doc["participants"] if p["adherent_id"] == competition["member"]["id"])


def test_competitors_shown_offline_other_changes_refused(mobile_page, competition):
    member = competition["member"]
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    expect(emergency_links(page, member)).to_have_count(1)  # the seed fills the first contact only

    contacts = wait_stored(page, "competitors", lambda data: any(c["adherent_id"] == member["id"] for c in data))
    contact = next(c for c in contacts if c["adherent_id"] == member["id"])
    # Contacts only: no health, address or e-mail data on the phone (plan O2)
    assert set(contact) == {"adherent_id", "last_name", "first_name", "phone", "creneau_groupe",
                            "emergency1_name", "emergency1_phone", "emergency2_name", "emergency2_phone"}
    go_offline(page, mobile_page.context, competition)
    try:
        expect(page.get_by_test_id("detail-name")).to_have_text(competition["nom"])
        expect(emergency_links(page, member)).to_have_count(1)
        page.get_by_test_id("load-group").click()  # any other change needs the network
        expect(toast(page)).to_contain_text("Hors ligne : seules les cases « Participe » et « Présent »")
    finally:
        mobile_page.context.set_offline(False)


def test_change_made_offline_is_sent_later(mobile_page, test_data, competition):
    member = competition["member"]
    context = mobile_page.context
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    go_offline(page, context, competition)
    try:
        card = participant_card(page, member)
        card.get_by_test_id("participe-switch").click()
        expect(card.get_by_test_id("queued")).to_be_visible()
        card.get_by_test_id("present-switch").click()  # the same competitor, the other flag
        expect(page.locator("#sync-info")).to_contain_text("2 modifications à envoyer")
        expect(page.get_by_test_id("kpi-selected")).to_have_text("0")
        assert participant(test_data, competition)["selectionne"] is True  # not sent yet
        # Kept on the device: still there after a restart without network (the page itself needs the network to
        # load here: service workers are blocked)
        context.set_offline(False)
        page.reload()
        context.set_offline(True)
        expect(participant_card(page, member).get_by_test_id("queued")).to_be_visible()
    finally:
        go_online(page, context)
    expect(toast(page)).to_contain_text("Modifications faites hors ligne envoyées", timeout=30_000)

    def sent():
        p = participant(test_data, competition)
        assert (p["selectionne"], p.get("present")) == (False, True)
    eventually(sent)
    expect(participant_card(page, member).get_by_test_id("queued")).to_have_count(0)
    assert queued(page) == []


def test_change_made_offline_is_refused_when_changed_elsewhere(mobile_page, test_data, competition):
    """Coach A unselects offline; meanwhile the office unselects and selects again: A's older change must not
    overwrite that newer decision."""
    member = competition["member"]
    context = mobile_page.context
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    go_offline(page, context, competition)
    try:
        participant_card(page, member).get_by_test_id("participe-switch").click()
        expect(participant_card(page, member).get_by_test_id("queued")).to_be_visible()
        test_data.set_selection(competition["id"], member["id"], False)
        test_data.set_selection(competition["id"], member["id"], True)
    finally:
        go_online(page, context)
    expect(toast(page)).to_contain_text("refusée", timeout=30_000)
    expect(toast(page)).to_contain_text("modifié entre-temps sur un autre appareil")
    assert participant(test_data, competition)["selectionne"] is True
    expect(participant_card(page, member).get_by_test_id("queued")).to_have_count(0)
    expect(page.get_by_test_id("kpi-selected")).to_have_text("1")


def test_change_queued_by_the_former_page_is_sent(mobile_page, test_data, competition):
    """Existing users' unsent changes carry over: an entry as web/competitions.html queued it is sent by the app."""
    member = competition["member"]
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    seen = participant(test_data, competition)["updated_at"]
    put_queued(page, {
        "key": f"{competition['id']}:{member['id']}:selectionne", "uid": owner(page), "flag": "selectionne", "value": False,
        "url": f"/api/competitions/{competition['id']}/participants/{member['id']}", "unchanged_since": seen,
        "label": f"{member['nom']} {member['prenom']} ({competition['nom']})", "queuedAt": 1,
    })
    page.reload()
    expect(toast(page)).to_contain_text("Modifications faites hors ligne envoyées", timeout=30_000)

    def sent():
        assert participant(test_data, competition)["selectionne"] is False
    eventually(sent)


def test_logout_with_changes_not_sent_asks_first(mobile_page, competition):
    member = competition["member"]
    context = mobile_page.context
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    go_offline(page, context, competition)
    try:
        participant_card(page, member).get_by_test_id("present-switch").click()
        expect(participant_card(page, member).get_by_test_id("queued")).to_be_visible()
        messages = []

        def answer(dialog):
            messages.append(dialog.message)
            if len(messages) == 1:
                dialog.dismiss()  # kept signed in
            else:
                dialog.accept()
        page.on("dialog", answer)
        # The box opens after the click has returned (the outbox is read first). Waited through Playwright: the
        # handler only runs inside a Playwright call, never during the time.sleep of eventually()
        with page.expect_event("dialog"):
            page.locator("#logout-btn").click()
        assert messages == ["1 modification faite hors ligne pas encore envoyée sera perdue. Se déconnecter ?"]
        expect(page.locator("#logout-btn")).to_be_visible()
        expect(participant_card(page, member).get_by_test_id("queued")).to_be_visible()
        page.locator("#logout-btn").click()
        expect(page.locator("#gate-login")).to_be_visible()

        def wiped():
            assert queued(page) == [] and stored(page, "competitions") is None
        eventually(wiped)
    finally:
        context.set_offline(False)


def test_logout_wipes_the_store(mobile_page, competition):
    page = open_screen(mobile_page)
    wait_stored(page, "competitors")
    page.locator("#logout-btn").click()
    expect(page.locator("#gate-login")).to_be_visible()

    def wiped():
        assert stored(page, "competitions") is None and stored(page, "competitors") is None
    eventually(wiped)


def test_readonly_keeps_no_contacts(mobile_page, competition):
    page = open_screen(mobile_page, role="readonly")
    wait_stored(page, "competitions")
    assert stored(page, "competitors") is None
