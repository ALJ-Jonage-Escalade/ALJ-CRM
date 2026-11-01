"""Office portal, Accueil: first page of the Vue app (frontend/), one responsive layout for every screen."""
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from helpers.auth import login_as

VERSION = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
NAV = "nav[aria-label='Navigation principale']"


def test_phone_layout(mobile_page):
    """Bottom navigation bar, no horizontal scroll, version in the footer."""
    mobile_page.goto("/bureau/")
    login_as(mobile_page, "coach")
    expect(mobile_page.locator("#content")).to_be_visible()
    assert mobile_page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")

    viewport = mobile_page.viewport_size
    nav = mobile_page.locator(NAV).bounding_box()
    assert abs(nav["y"] + nav["height"] - viewport["height"]) <= 1, "navigation bar at the bottom of the screen"
    assert nav["width"] == viewport["width"]
    expect(mobile_page.locator(f"{NAV} a")).to_have_count(6)  # a coach: no Communications, no Paramètres
    # The directory instead of Adhérents in the menu (both pages still open by their address)
    expect(mobile_page.locator(f"{NAV} a").filter(visible=True)).to_have_count(5)
    expect(mobile_page.locator(f"{NAV} a[data-page='annuaire']")).to_be_visible()
    expect(mobile_page.locator(f"{NAV} a[data-page='adherents']")).to_be_hidden()
    expect(mobile_page.get_by_text(f"v{VERSION}", exact=True).filter(visible=True)).to_be_visible()


def test_desktop_layout(page):
    """Side menu with the version; no page links in the content, the menu already lists them."""
    page.goto("/bureau/")
    login_as(page, "admin")
    expect(page.locator("#content")).to_contain_text("Connecté en tant que administrateur")
    nav = page.locator(NAV).bounding_box()
    assert nav["x"] < 50 and nav["height"] > 200, "vertical menu on the left"
    expect(page.locator(f"{NAV} a[data-page='accueil']")).to_have_attribute("aria-current", "page")
    # Adhérents instead of the directory in the menu
    expect(page.locator(f"{NAV} a[data-page='adherents']")).to_be_visible()
    expect(page.locator(f"{NAV} a[data-page='annuaire']")).to_be_hidden()
    for href in ["/bureau/adherents", "/index", "/bureau/planning", "/bureau/parametres"]:
        expect(page.locator(f"#content a[href='{href}']")).to_have_count(0)
    expect(page.get_by_text(f"v{VERSION}", exact=True).filter(visible=True)).to_be_visible()

    page.locator("#content a[href='/bureau/competitions']").first.click()  # « Tout voir » of the widget
    page.wait_for_url(re.compile(r"/bureau/competitions(\?id=[^&]+)?$"))  # the first competition opens by itself
    expect(page.locator("#who")).to_contain_text("albus.dumbledore@alj-escalade.fr")  # same session on the page


ADMIN_PAGES = ["communications", "parametres", "administration"]


@pytest.mark.parametrize("role, count", [("admin", 9), ("coach", 6)])
def test_menu_follows_the_role(page, role, count):
    page.goto("/bureau/")
    login_as(page, role)
    expect(page.locator("#content")).to_be_visible()
    expect(page.locator(f"{NAV} a")).to_have_count(count)
    for name in ADMIN_PAGES:
        shown = 1 if role == "admin" else 0
        expect(page.locator(f"{NAV} a[data-page='{name}']")).to_have_count(shown)


@pytest.mark.parametrize("role, pages", [("readonly", ["competitions"]), ("stranger", [])])
def test_non_staff_sees_no_office_menu(page, role, pages):
    """A read-only account only reaches the competitions (as on the former phone page)."""
    page.goto("/bureau/")
    login_as(page, role)
    expect(page.locator("#gate")).to_contain_text("Accès réservé")
    expect(page.locator("nav")).to_have_count(0)  # full-screen gate: the pages it may open are listed in it
    expect(page.locator("#gate a")).to_have_count(len(pages))
    for name in pages:
        expect(page.locator(f"#gate a[data-page='{name}']")).to_be_visible()


@pytest.mark.parametrize("name, label", [("parametres", "Paramètres"), ("communications", "Communications"),
                                         ("administration", "Administration")])
def test_coach_is_sent_back_from_an_admin_page(page, name, label):
    """Vue app: the router guards send a coach back to Accueil, which names the page."""
    page.goto(f"/bureau/{name}")
    login_as(page, "coach")
    page.wait_for_url(f"**/bureau/?reserve=/bureau/{name}")
    expect(page.locator("#refused-page")).to_have_text(f"⛔ La page {label} est réservée aux administrateurs.")
    expect(page.locator(f"{NAV} a[data-page='{name}']")).to_have_count(0)


def test_admin_opens_admin_pages(page):
    """Paramètres → Communications: routes of the Vue app, no page load."""
    page.goto("/bureau/parametres")
    login_as(page, "admin")
    expect(page.locator("#content")).to_be_visible()
    expect(page.locator("#gate")).to_be_hidden()
    page.evaluate("() => { window.__sameDocument = true; }")
    page.locator(f"{NAV} a[data-page='communications']").filter(visible=True).click()
    page.wait_for_url("**/bureau/communications")
    expect(page.get_by_test_id("template-select").locator("option").first).to_be_attached()
    assert page.evaluate("() => window.__sameDocument") is True


def test_in_app_navigation_keeps_the_page_loaded(page):
    """Accueil → Paramètres → Accueil are routes of the same app: no page load, the session stays."""
    page.goto("/bureau/")
    login_as(page, "admin")
    expect(page.locator("#content")).to_be_visible()
    page.evaluate("() => { window.__sameDocument = true; }")
    page.locator(f"{NAV} a[data-page='parametres']").filter(visible=True).click()
    expect(page.get_by_test_id("cache-status")).to_contain_text("Cache opérationnel")
    page.locator(f"{NAV} a[data-page='accueil']").filter(visible=True).click()
    expect(page.get_by_test_id("home-widgets")).to_be_visible()
    assert page.evaluate("() => window.__sameDocument") is True


def test_refused_page_notice(page):
    """Where the router guards send a coach from an admin page; an unknown page is not named."""
    page.goto("/bureau/?reserve=/bureau/parametres")
    login_as(page, "coach")
    expect(page.locator("#refused-page")).to_have_text("⛔ La page Paramètres est réservée aux administrateurs.")
    page.goto("/bureau/?reserve=/autre")
    expect(page.locator("#content")).to_be_visible()
    expect(page.locator("#refused-page")).to_have_count(0)
