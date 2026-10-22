"""Office portal, Accueil: first page of the Vue app (frontend/), one responsive layout for every screen."""
from pathlib import Path

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
    expect(mobile_page.locator(f"{NAV} a")).to_have_count(7)
    expect(mobile_page.get_by_text(f"v{VERSION}", exact=True).filter(visible=True)).to_be_visible()


def test_desktop_layout(page):
    """Side menu with the version; the cards lead to the pages not migrated yet."""
    page.goto("/bureau/")
    login_as(page, "admin")
    expect(page.locator("#content")).to_contain_text("Connecté en tant que administrateur")
    nav = page.locator(NAV).bounding_box()
    assert nav["x"] < 50 and nav["height"] > 200, "vertical menu on the left"
    expect(page.locator(f"{NAV} a[data-page='accueil']")).to_have_attribute("aria-current", "page")
    expect(page.get_by_text(f"v{VERSION}", exact=True).filter(visible=True)).to_be_visible()

    page.locator("#content a[href='/bureau/planning']").click()
    page.wait_for_url("**/bureau/planning")
    expect(page.locator("#who")).to_contain_text("albus.dumbledore@alj-escalade.fr")  # same session on the former page
