"""Office portal members (Vue app, /bureau/adherents): the list and the member record (a dialog of the page, in the
URL as ?id=…&saison=…&achat=…): navigation and locators."""
import re

from playwright.sync_api import Locator, Page, expect

from helpers.auth import login_as

ROWS = "data-row"       # rows of the list (desktop table)


def open_members(page: Page, role: str = "admin") -> Page:
    page.goto("/bureau/adherents")
    login_as(page, role)
    expect(page.get_by_test_id(ROWS).first).to_be_visible(timeout=20_000)
    return page


def displayed_count(page: Page) -> int:
    """« N adhérents affichés sur M (saison …) » → N."""
    return int(re.match(r"\d+", page.get_by_test_id("member-count").inner_text()).group())


def find(page: Page, member: dict) -> Locator:
    """Searches the member (by last name) and returns their row."""
    page.get_by_test_id("member-search").fill(member["nom"])
    return page.get_by_test_id(ROWS).filter(has_text=member["prenom"]).filter(has_text=member["nom"].upper())


def open_record(page: Page, member: dict, role: str = "admin") -> Locator:
    """Opens the member's record from the list (dialog of the page) and returns it."""
    open_members(page, role)
    find(page, member).get_by_test_id("member-record").click()
    dialog = page.get_by_test_id("record-dialog")
    expect(dialog.get_by_test_id("record-name")).to_have_text(f"{member['prenom']} {member['nom'].upper()}")
    return dialog
