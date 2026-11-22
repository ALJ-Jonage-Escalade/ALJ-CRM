"""Competitions screen of the Vue app (frontend/src/pages/CompetitionsPage.vue, on /competitions and
/bureau/competitions): navigation and locators (data-testid)."""
from playwright.sync_api import Locator, Page, expect

from helpers.auth import login_as

# Always present after the seed: proves the competitions have been loaded
SEEDED_COMPETITION = "Hogwarts Lead Open"


def open_screen(page: Page, role: str = "coach", path: str = "/competitions") -> Page:
    page.goto(path)
    login_as(page, role)
    # First load, slower while other workers run
    expect(competition_card(page, SEEDED_COMPETITION)).to_be_visible(timeout=20_000)
    return page


def competition_card(page: Page, nom: str) -> Locator:
    """Card of a competition in the list (the archives too, once shown)."""
    return page.get_by_test_id("comp-card").filter(has=page.get_by_test_id("comp-name").get_by_text(nom, exact=True))


def archived_card(page: Page, nom: str) -> Locator:
    return page.get_by_test_id("archived-list").get_by_test_id("comp-card").filter(has_text=nom)


def open_competition(page: Page, nom: str) -> Locator:
    """Opens the competition (the list stays beside it on desktop, it is hidden on a phone)."""
    competition_card(page, nom).click()
    expect(page.get_by_test_id("detail-name")).to_have_text(nom)
    return page.get_by_test_id("comp-detail")


def sub_menu_entry(page: Page, sub_page: str) -> Locator:
    """Entry of a sub-page in the menu shown: nested in the side menu on desktop, the strip under the title on phones
    (frontend/src/components/SubNav.vue; none on Compétitions, whose sub-pages are tested on desktop)."""
    return page.locator(f"[data-testid='sub-side-{sub_page}']:visible, [data-testid='sub-strip-{sub_page}']:visible")


def go_to(page: Page, sub_page: str) -> None:
    """Sub-pages of coaches and admins: competitions, helloasso, bilan, coachs."""
    sub_menu_entry(page, sub_page).click()
    expect(sub_menu_entry(page, sub_page)).to_have_attribute("aria-current", "page")


def participant_card(page: Page, member: dict) -> Locator:
    return page.get_by_test_id("participant-card").filter(
        has=page.get_by_test_id("participant-name").get_by_text(f"{member['nom']} {member['prenom']}", exact=True))


def toast(page: Page) -> Locator:
    return page.locator("#toast")
