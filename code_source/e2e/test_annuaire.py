"""Members directory (/index, Vue app: frontend/src/pages/AnnuairePage.vue), on phones and desktop: search, member
cards, emergency contacts, filters, roles; and its offline copy (IndexedDB, frontend/src/lib/store.ts): shown with its
date when the network is down, wiped on logout, on a 403, for another account and after 30 days.

Service workers are blocked in the e2e contexts, so "offline" is simulated by making every API call fail while the
page itself still loads."""
import re

import pytest
from playwright.sync_api import Page, expect

from helpers.auth import login_as, open_menu
from helpers.data import eventually
from helpers.offline import age, record, stored, wait_stored

CARD = "directory-card"


def open_directory(page: Page, role: str = "coach") -> Page:
    page.goto("/index")
    login_as(page, role)
    expect(page.get_by_test_id(CARD).first).to_be_visible(timeout=20_000)
    return page


def shown(page: Page) -> int:
    return int(page.get_by_test_id("kpi-shown").inner_text())


def card(page: Page, member: dict):
    return page.get_by_test_id(CARD).filter(has_text=f"{member['prenom']} {member['nom']}")


def assert_wiped(page: Page) -> None:
    assert record(page, "directory") is None, "directory still stored"


def api_down(page: Page) -> None:
    """Restarted with the API unreachable, then the network cut."""
    page.context.route("**/api/**", lambda route: route.abort("internetdisconnected"))
    page.reload()
    page.context.set_offline(True)


def api_back(page: Page) -> None:
    page.context.unroute("**/api/**")
    page.context.set_offline(False)


@pytest.fixture(scope="module")
def member(test_data):
    """A seeded member with a phone number (some seeded records are deliberately incomplete)."""
    return next(m for m in sorted(test_data.members(), key=lambda m: m["nom"]) if m.get("phone"))


def test_search_and_member_card(mobile_page, member):
    page = open_directory(mobile_page)
    total = shown(page)
    assert total > 20
    page.get_by_test_id("directory-search").fill(member["nom"].lower())
    expect(card(page, member)).to_have_count(1)
    assert shown(page) < total

    expect(card(page, member).get_by_test_id("card-details")).to_have_count(0)
    card(page, member).get_by_test_id("card-toggle").click()
    expect(card(page, member).get_by_test_id("card-details")).to_contain_text(member["email"])
    expect(card(page, member).get_by_role("link", name="Appeler")).to_have_attribute("href", re.compile(r"^tel:\+?\d+$"))
    assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"), "no horizontal scroll"


def test_emergency_contacts(mobile_page, member):
    page = open_directory(mobile_page)
    page.get_by_test_id("tab-urgency").click()
    expect(page.get_by_test_id("urgency-count")).to_contain_text("au moins 2 lettres")
    page.get_by_test_id("urgency-search").fill(member["nom"])
    found = page.get_by_test_id("urgency-card").filter(has_text=f"{member['prenom']} {member['nom']}")
    expect(found).to_have_count(1)
    expect(found).to_contain_text("Urgence 1")
    expect(found.get_by_role("link", name="Appeler").first).to_have_attribute("href", re.compile(r"^tel:"))


def test_season_and_slot_filters(mobile_page):
    page = open_directory(mobile_page)
    total = shown(page)
    expect(page.get_by_test_id("directory-filters")).to_be_hidden()
    page.get_by_test_id("tab-filters").click()
    page.get_by_test_id("filter-none").click()
    expect(page.get_by_test_id("kpi-shown")).to_have_text("0")
    page.get_by_test_id("filter-all").click()
    assert shown(page) >= total

    page.get_by_test_id("season-select").select_option(index=1)
    page.get_by_test_id("tab-members").click()
    expect(page.get_by_test_id("directory-count")).to_contain_text("saison 2025-2026")
    assert shown(page) != total


def test_desktop_shows_filters_beside_the_list(page):
    open_directory(page)
    expect(page.get_by_test_id("directory-filters")).to_be_visible()
    expect(page.get_by_test_id("tab-filters")).to_be_hidden()
    expect(page.locator("nav a[data-page='annuaire']")).to_have_attribute("aria-current", "page")


@pytest.mark.parametrize("role", ["readonly", "stranger"])
def test_reserved_to_coaches(mobile_page, role):
    mobile_page.goto("/index")
    login_as(mobile_page, role)
    expect(mobile_page.locator("#gate")).to_contain_text("Accès réservé")
    expect(mobile_page.get_by_test_id(CARD)).to_have_count(0)
    assert stored(mobile_page, "directory") is None


# ---------------------------------------------------------------- Offline copy

def test_shown_offline_with_its_date(mobile_page, member):
    page = open_directory(mobile_page)
    members = wait_stored(page, "directory", lambda d: len(d["members"]) > 20)["members"]
    kept = next(m for m in members if m["last_name"].lower() == member["nom"].lower())
    assert kept["phone"] and "health_commitment" not in kept and "amount" not in kept  # contacts only
    api_down(page)
    try:
        expect(page.locator("#offline-notice")).to_be_visible()
        expect(card(page, member)).to_have_count(1)
        expect(page.locator("#sync-info")).to_contain_text(re.compile(r"Hors ligne — données du \d{2}/\d{2}/\d{4}"))
        page.get_by_test_id("tab-urgency").click()
        page.get_by_test_id("urgency-search").fill(member["nom"])
        expect(page.get_by_test_id("urgency-card")).to_contain_text("Urgence 1")
    finally:
        api_back(page)
    # Network back: the role is checked again and the list follows the server
    page.evaluate("() => window.dispatchEvent(new Event('online'))")
    expect(page.locator("#offline-notice")).to_have_count(0, timeout=20_000)
    expect(page.locator("#sync-info")).to_have_text("", timeout=20_000)


def test_logout_wipes_the_copy(mobile_page):
    page = open_directory(mobile_page)
    wait_stored(page, "directory")
    open_menu(page)
    page.locator("#logout-btn").click()
    expect(page.locator("#gate-login")).to_be_visible()
    eventually(lambda: assert_wiped(page))


def test_another_account_wipes_the_copy(mobile_page):
    page = open_directory(mobile_page, "coach")
    coach_uid = eventually(lambda: record(page, "directory")["uid"])
    login_as(page, "admin")  # over the coach's session, without logging out

    def admin_copy():
        rec = record(page, "directory")
        assert rec is not None and rec["uid"] != coach_uid, rec and rec["uid"]
    eventually(admin_copy, timeout=30)


def test_copy_older_than_30_days_is_wiped(mobile_page):
    page = open_directory(mobile_page)
    wait_stored(page, "directory")
    age(page, "directory", 31)
    api_down(page)
    try:
        expect(page.get_by_test_id("directory-count")).to_have_text("Aucune donnée de l'annuaire sur cet appareil.")
        expect(page.get_by_test_id(CARD)).to_have_count(0)
        assert record(page, "directory") is None
    finally:
        api_back(page)


def test_refused_list_wipes_the_copy(mobile_page):
    page = open_directory(mobile_page)
    wait_stored(page, "directory")
    page.context.route("**/api/members*", lambda route: route.fulfill(status=403, json={"status": "error", "message": "refusé"}))
    page.evaluate("() => window.dispatchEvent(new Event('online'))")  # polls now
    expect(page.locator("#sync-info")).to_have_text("🔒 Accès réservé aux coachs")
    expect(page.get_by_test_id(CARD)).to_have_count(0)
    eventually(lambda: assert_wiped(page))
