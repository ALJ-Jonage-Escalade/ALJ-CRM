"""Mobile app without network (docs/plan_api_only_front.md, phase 5a): the last data received is kept
in IndexedDB (web/shared/alj-store.js) and shown read-only; writes are refused. Competitors' emergency
contacts are kept for coaches only, and the store is wiped on logout.

Service workers are blocked in the e2e contexts, so "offline" is simulated by making every API call fail
while the page itself still loads."""
import pytest
from playwright.sync_api import expect

from helpers.data import eventually, unique_name
from helpers.mobile import competition_card, open_app, open_participants, participant_card, toast

_STORED = """async (name) => new Promise(resolve => {
  const req = indexedDB.open("alj-offline");
  req.onerror = () => resolve(null);
  req.onsuccess = () => {
    const db = req.result;
    if (!db.objectStoreNames.contains("resources")) { db.close(); resolve(null); return; }
    const get = db.transaction("resources").objectStore("resources").get(name);
    get.onsuccess = () => { db.close(); resolve(get.result ? get.result.data : null); };
    get.onerror = () => { db.close(); resolve(null); };
  };
})"""


def stored(page, name):
    return page.evaluate(_STORED, name)


def wait_stored(page, name, check=lambda data: True):
    """The page saves after rendering: retried until the record is there and passes `check`."""
    def ready():
        data = stored(page, name)
        assert data is not None and check(data), data
        return data
    return eventually(ready)


@pytest.fixture
def competition(test_data):
    member = test_data.members(competition_only=True)[0]
    nom = unique_name("E2E Offline")
    cid = test_data.create_competition(nom, date="2027-12-04", participants=[member["id"]],
                                       selected=[member["id"]])
    return {"id": cid, "nom": nom, "member": member}


def emergency_links(page, member):
    return participant_card(page, member).locator("a[title=\"Contact d'urgence\"]")


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
        participant_card(page, member).locator(".switch").click()
        expect(toast(page)).to_contain_text("Hors ligne : modification impossible")
    finally:
        mobile_context.set_offline(False)


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
