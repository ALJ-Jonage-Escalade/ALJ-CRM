"""Competitions screen of the Vue app (frontend/src/pages/CompetitionsPage.vue), reading, on /competitions and
/bureau/competitions (changes: test_competitions_manage.py, test_competitors.py, test_offline.py…): list, participants and payment status, roles, offline copy (shared with the former page), the
Google sign-in that ends on /competitions, and the installed app.

Service workers are blocked in the e2e contexts (except where allowed), so "offline" is simulated by making every API
call fail while the page itself still loads."""
import re
import time

import pytest
from playwright.sync_api import Page, expect

from helpers.auth import ACCOUNTS, login_as, open_menu
from helpers.data import unique_name
from helpers.competitions import SEEDED_COMPETITION, sub_menu_entry
from helpers.offline import owner, put_record, record, wait_stored
from helpers.stack import AUTH_HOST


def open_view(page: Page, role: str = "coach", path: str = "/competitions") -> Page:
    page.goto(path)
    login_as(page, role)
    expect(card(page, SEEDED_COMPETITION)).to_be_visible(timeout=20_000)
    return page


def card(page: Page, nom: str):
    return page.get_by_test_id("comp-card").filter(has=page.get_by_test_id("comp-name").get_by_text(nom, exact=True))


def api_down(page: Page) -> None:
    page.context.route("**/api/**", lambda route: route.abort("internetdisconnected"))
    page.reload()
    page.context.set_offline(True)


def api_back(page: Page) -> None:
    page.context.unroute("**/api/**")
    page.context.set_offline(False)


@pytest.fixture
def competition(test_data):
    """A competition with one selected competitor (who has an emergency contact in the seed)."""
    member = test_data.competition_group()[0]
    nom = unique_name("E2E Vue")
    cid = test_data.create_competition(nom, date="2027-11-20", participants=[member["id"]], selected=[member["id"]])
    return {"id": cid, "nom": nom, "member": member}


def participant(page: Page, member: dict):
    return page.get_by_test_id("participant-card").filter(
        has=page.get_by_test_id("participant-name").get_by_text(f"{member['nom']} {member['prenom']}", exact=True))


def test_phone_list_then_competition(mobile_page, competition):
    page = open_view(mobile_page)
    expect(page.get_by_test_id("view-switcher")).to_be_hidden()  # the cards only: no table nor calendar on a phone
    card(page, competition["nom"]).click()
    expect(page.get_by_test_id("detail-name")).to_have_text(competition["nom"])
    expect(page).to_have_url(re.compile(rf"/competitions\?id={competition['id']}$"))
    expect(card(page, SEEDED_COMPETITION)).to_be_hidden()  # one at a time on a phone
    expect(page.get_by_test_id("subnav-strip")).to_have_count(0)  # the main page only: the sub-pages are for a computer
    expect(page.get_by_test_id("actions-guide")).to_be_hidden()  # a computer read
    row = participant(page, competition["member"])
    expect(row.get_by_test_id("participe-switch")).to_be_checked()
    expect(row.get_by_test_id("payment-badge")).to_be_visible()
    expect(row.get_by_test_id("emergency-link")).to_have_count(1)
    # Filtered by slot group on a phone (the competition day), not by registration
    expect(page.get_by_test_id("filter-selected")).to_have_count(0)
    expect(page.get_by_test_id("participant-search")).to_have_count(0)
    group_filter = page.get_by_test_id("group-filter")
    expect(group_filter.locator("option")).to_have_count(2)  # « Tous » and the competitor's group
    group_filter.select_option(index=1)
    expect(row).to_be_visible()
    assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"), "no horizontal scroll"
    page.get_by_test_id("back-link").click()
    expect(card(page, SEEDED_COMPETITION)).to_be_visible()


def test_desktop_shows_list_and_competition_side_by_side(page, competition):
    open_view(page, "admin", "/bureau/competitions")
    # The page is the current section, its index sub-page the current page (plans/sub-menus.md D3)
    expect(page.locator("nav a[data-page='competitions']")).to_have_attribute("aria-current", "true")
    expect(sub_menu_entry(page, "competitions")).to_have_attribute("aria-current", "page")
    card(page, competition["nom"]).click()
    expect(page.get_by_test_id("detail-name")).to_have_text(competition["nom"])
    expect(card(page, SEEDED_COMPETITION)).to_be_visible()


def test_both_addresses_show_the_same_screen(page):
    for path in ("/competitions", "/competitions?vue=mobile", "/bureau/competitions"):
        page.goto(path)
        expect(page).to_have_url(re.compile(re.escape(path) + "$"))  # no device redirection any more
        expect(page.locator("#gate-login")).to_be_visible()


def test_readonly_sees_no_contacts_nor_management(mobile_page, competition):
    page = open_view(mobile_page, "readonly")
    open_menu(page)
    expect(page.locator("nav a[data-page='competitions']")).to_be_visible()
    page.locator("#menu-toggle").click()  # closed again
    card(page, competition["nom"]).click()
    expect(participant(page, competition["member"])).to_be_visible()
    expect(page.get_by_test_id("emergency-link")).to_have_count(0)
    expect(participant(page, competition["member"]).get_by_test_id("participe")).to_have_text("✅ Participe")
    for testid in ("participe-switch", "participant-actions", "detail-actions", "detail-more", "create-comp", "subnav-side",
                   "subnav-strip"):
        expect(page.get_by_test_id(testid)).to_have_count(0)


def test_account_without_role_is_refused(mobile_page):
    mobile_page.goto("/competitions")
    login_as(mobile_page, "stranger")
    expect(mobile_page.locator("#gate")).to_contain_text("Accès réservé")
    expect(mobile_page.get_by_test_id("comp-card")).to_have_count(0)


def test_shown_offline_with_its_date(mobile_page, competition):
    page = open_view(mobile_page)
    card(page, competition["nom"]).click()
    wait_stored(page, "competitions", lambda data: any(c["id"] == competition["id"] for c in data), timeout=30)
    wait_stored(page, "competitors", lambda data: any(c["adherent_id"] == competition["member"]["id"] for c in data))
    api_down(page)
    try:
        expect(page.locator("#offline-notice")).to_be_visible()
        expect(page.get_by_test_id("detail-name")).to_have_text(competition["nom"])
        expect(participant(page, competition["member"]).get_by_test_id("emergency-link")).to_have_count(1)
        expect(page.locator("#sync-info")).to_contain_text(re.compile(r"Hors ligne — données du \d{2}/\d{2}/\d{4}"))
    finally:
        api_back(page)


def test_copy_of_the_former_page_is_shown_offline(mobile_page, competition, test_data):
    """Existing users' offline data carries over: a copy as the former page's alj-store.js kept it (no url)."""
    page = open_view(mobile_page)
    put_record(page, {"name": "competitions", "uid": owner(page), "savedAt": int(time.time() * 1000), "etag": None,
                      "data": [test_data.competition(competition["id"])]})
    assert record(page, "competitions").get("url") is None
    api_down(page)
    try:
        expect(card(page, competition["nom"])).to_be_visible()
    finally:
        api_back(page)


def test_sign_in_ends_on_competitions(page):
    """Real flow from the screen itself: gate → /competitions?login=1 → emulator picker → back, signed in."""
    page.goto("/competitions")
    page.locator("#gate-login").click()
    page.wait_for_url(re.compile(re.escape(AUTH_HOST) + "/emulator/auth/handler"))
    page.get_by_text(ACCOUNTS["coach"].email).click()
    page.wait_for_url(re.compile(r"/competitions(\?id=[^&]+)?$"))  # desktop: the first competition opens by itself
    expect(page.locator("#who")).to_contain_text(ACCOUNTS["coach"].email)
    expect(card(page, SEEDED_COMPETITION)).to_be_visible(timeout=20_000)


def test_former_management_addresses_open_the_screen(page, competition):
    """Bookmarks of the former management pages (until plan phase 11) open the competitions screen."""
    page.goto("/competitions/gestion")
    expect(page).to_have_url(re.compile(r"/competitions$"))
    page.goto(f"/bureau/competitions-gestion?id={competition['id']}")
    expect(page).to_have_url(re.compile(rf"/bureau/competitions\?id={competition['id']}$"))
    login_as(page, "admin")
    expect(page.get_by_test_id("detail-name")).to_have_text(competition["nom"])


@pytest.mark.browser_context_args(service_workers="allow")
def test_installs_and_opens_as_an_app(page):
    page.goto("/competitions")
    expect(page.locator("link[rel=manifest]")).to_have_attribute("href", "/manifest.webmanifest")
    manifest = page.request.get("/manifest.webmanifest").json()
    assert manifest["start_url"] == "/competitions" and manifest["display"] == "standalone"
    page.evaluate("() => navigator.serviceWorker.ready")
    assert page.evaluate("() => navigator.serviceWorker.getRegistrations().then(r => r.length)") >= 1
