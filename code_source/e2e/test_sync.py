"""Two coaches on two phones: a change made on one shows up on the other without reloading.

The screen polls the API every 20 s, hence the generous timeout."""
import pytest
from playwright.sync_api import expect

from helpers.data import unique_name
from helpers.competitions import competition_card, open_competition, open_screen, participant_card

pytestmark = pytest.mark.slow
SYNC_TIMEOUT = 30_000


@pytest.fixture
def second_phone(new_context, playwright):
    device = {k: v for k, v in playwright.devices["Pixel 7"].items() if k != "default_browser_type"}
    return new_context(**device).new_page()


def test_new_competition_reaches_other_phone(mobile_page, second_phone):
    first, second = open_screen(mobile_page), open_screen(second_phone)
    nom = unique_name("E2E Sync")
    first.get_by_test_id("create-comp").click()
    first.get_by_test_id("cf-nom").fill(nom)
    first.get_by_test_id("cf-date").fill("2027-10-02")
    first.get_by_test_id("cf-save").click()
    expect(first.get_by_test_id("detail-name")).to_have_text(nom)
    expect(competition_card(second, nom)).to_be_visible(timeout=SYNC_TIMEOUT)


def test_selection_reaches_other_phone(mobile_page, second_phone, test_data):
    member = test_data.members(competition_only=True)[0]
    nom = unique_name("E2E Sync")
    test_data.create_competition(nom, date="2027-10-03", participants=[member["id"]])
    first, second = open_screen(mobile_page), open_screen(second_phone)
    open_competition(first, nom)
    open_competition(second, nom)
    participant_card(first, member).get_by_test_id("participe-switch").click()
    expect(second.get_by_test_id("kpi-selected")).to_have_text("1", timeout=SYNC_TIMEOUT)
    expect(participant_card(second, member).get_by_test_id("participe-switch")).to_be_checked()
