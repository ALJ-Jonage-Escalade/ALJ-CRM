"""Mobile app without network (documentations/plan_api_only_front.md, phase 5): the last data received is kept
in IndexedDB (web/shared/alj-store.js). Competitors' emergency contacts are kept for coaches only, and
the store is wiped on logout. Offline, only « Participe » can be changed (5b): kept in the outbox and
sent when the network comes back, refused if the participant changed meanwhile.

Service workers are blocked in the e2e contexts, so "offline" is simulated by making every API call fail
while the page itself still loads."""
import pytest
from playwright.sync_api import expect

from helpers.data import eventually, unique_name
from helpers.mobile import competition_card, open_app, open_participants, participant_card, toast
from helpers.offline import stored, wait_stored


@pytest.fixture
def competition(test_data):
    member = test_data.members(competition_only=True)[0]
    nom = unique_name("E2E Offline")
    cid = test_data.create_competition(nom, date="2027-12-04", participants=[member["id"]],
                                       selected=[member["id"]])
    return {"id": cid, "nom": nom, "member": member}


def emergency_links(page, member):
    return participant_card(page, member).locator("a[title=\"Contact d'urgence\"]")


def go_offline(page, mobile_context, competition) -> None:
    """Page restarted from the store with the API unreachable, then the network cut."""
    # Up to one poll (20 s): the server caches the competition list for 5 s
    wait_stored(page, "competitions", lambda data: any(c["id"] == competition["id"] for c in data), timeout=30)
    mobile_context.route("**/api/**", lambda route: route.abort("internetdisconnected"))
    page.reload()
    expect(competition_card(page, competition["nom"])).to_be_visible()
    mobile_context.set_offline(True)
    expect(page.locator("#sync-info")).to_contain_text("Hors ligne")


def go_online(page, mobile_context) -> None:
    mobile_context.unroute("**/api/**")
    mobile_context.set_offline(False)


def participe(test_data, competition) -> bool:
    doc = test_data.competition(competition["id"])
    return next(p for p in doc["participants"] if p["adherent_id"] == competition["member"]["id"])["selectionne"]


def test_competitors_shown_offline_read_only(mobile_page, mobile_context, competition):
    member = competition["member"]
    page = open_app(mobile_page)
    open_participants(page, competition["nom"])
    expect(emergency_links(page, member)).to_have_count(1)  # the seed fills the first contact only

    contacts = wait_stored(page, "competitors",
                           lambda data: any(c["adherent_id"] == member["id"] for c in data))
    contact = next(c for c in contacts if c["adherent_id"] == member["id"])
    # Contacts only: no health, address or e-mail data on the phone (plan O2)
    assert set(contact) == {"adherent_id", "last_name", "first_name", "phone", "creneau_groupe",
                            "emergency1_name", "emergency1_phone", "emergency2_name", "emergency2_phone"}
    wait_stored(page, "competitions",
                lambda data: any(c["id"] == competition["id"] for c in data))

    mobile_context.route("**/api/**", lambda route: route.abort("internetdisconnected"))
    page.reload()
    expect(competition_card(page, competition["nom"])).to_be_visible()
    mobile_context.set_offline(True)
    try:
        expect(page.locator("#sync-info")).to_contain_text("Hors ligne")
        open_participants(page, competition["nom"])
        expect(emergency_links(page, member)).to_have_count(1)
        page.locator("#p-load-group").click()  # any other change needs the network
        expect(toast(page)).to_contain_text("Hors ligne : seule la case « Participe »")
    finally:
        mobile_context.set_offline(False)


def test_change_made_offline_is_sent_later(mobile_page, mobile_context, test_data, competition):
    member = competition["member"]
    page = open_app(mobile_page)
    go_offline(page, mobile_context, competition)
    try:
        open_participants(page, competition["nom"])
        participant_card(page, member).locator(".switch").click()
        expect(participant_card(page, member)).to_contain_text("à envoyer")
        expect(page.locator("#sync-info")).to_contain_text("1 modification à envoyer")
        expect(page.locator("#p-kpi-participe")).to_have_text("0")
        assert participe(test_data, competition) is True  # not sent yet
        # Kept on the phone: still there after a restart without network (the page itself
        # needs the network to load here: service workers are blocked)
        mobile_context.set_offline(False)
        page.reload()
        mobile_context.set_offline(True)
        open_participants(page, competition["nom"])
        expect(participant_card(page, member)).to_contain_text("à envoyer")
    finally:
        go_online(page, mobile_context)
    page.evaluate("() => window.dispatchEvent(new Event('online'))")
    expect(toast(page)).to_contain_text("Modifications faites hors ligne envoyées", timeout=30_000)

    def sent():
        assert participe(test_data, competition) is False
    eventually(sent)
    expect(participant_card(page, member)).not_to_contain_text("à envoyer")


def test_change_made_offline_is_refused_when_changed_elsewhere(mobile_page, mobile_context, test_data,
                                                              competition):
    """Coach A unselects offline; meanwhile the desktop app unselects and selects again: A's older
    change must not overwrite that newer decision."""
    member = competition["member"]
    page = open_app(mobile_page)
    go_offline(page, mobile_context, competition)
    try:
        open_participants(page, competition["nom"])
        participant_card(page, member).locator(".switch").click()
        expect(participant_card(page, member)).to_contain_text("à envoyer")
        test_data.set_selection(competition["id"], member["id"], False)
        test_data.set_selection(competition["id"], member["id"], True)
    finally:
        go_online(page, mobile_context)
    page.evaluate("() => window.dispatchEvent(new Event('online'))")
    expect(toast(page)).to_contain_text("refusée", timeout=30_000)
    expect(toast(page)).to_contain_text("modifié entre-temps sur un autre appareil")
    assert participe(test_data, competition) is True
    expect(participant_card(page, member)).not_to_contain_text("à envoyer")
    expect(page.locator("#p-kpi-participe")).to_have_text("1")


def test_logout_wipes_the_store(mobile_page, competition):
    page = open_app(mobile_page)
    wait_stored(page, "competitors")
    page.evaluate("() => ALJFirebase.init().auth.signOut()")
    expect(page.locator("#setup-not-logged")).to_be_visible()
    def wiped():
        assert stored(page, "competitions") is None and stored(page, "competitors") is None
    eventually(wiped)


def test_readonly_keeps_no_contacts(mobile_page, competition):
    page = open_app(mobile_page, role="readonly")
    wait_stored(page, "competitions")
    assert stored(page, "competitors") is None
