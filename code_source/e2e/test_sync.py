"""Two coaches on two phones: a change made on one shows up on the other without reloading.

The screen polls the API every 20 s: the second phone's clock is faked, so that the tests jump to the next poll
instead of waiting for it."""
import pytest
from playwright.sync_api import expect

from helpers.data import eventually, unique_name
from helpers.competitions import competition_card, open_competition, open_screen, participant_card

POLL_INTERVAL_MS = 20_000   # frontend/src/lib/sync.ts
POLL_ANSWER_TIMEOUT = 1_000


@pytest.fixture
def second_phone(new_context, playwright):
    device = {k: v for k, v in playwright.devices["Pixel 7"].items() if k != "default_browser_type"}
    phone = new_context(**device).new_page()
    phone.clock.install()
    return phone


def _after_next_poll(phone, check) -> None:
    """Jumps to the next poll until `check` passes: a poll can run before the first phone's write reaches Firestore
    (the pages update optimistically), the following one then brings the change."""
    def jump_and_check():
        phone.clock.fast_forward(POLL_INTERVAL_MS)
        check()
    eventually(jump_and_check, timeout=15)


def test_new_competition_reaches_other_phone(mobile_page, second_phone):
    first, second = open_screen(mobile_page), open_screen(second_phone)
    nom = unique_name("E2E Sync")
    first.get_by_test_id("create-comp").click()
    first.get_by_test_id("cf-nom").fill(nom)
    first.get_by_test_id("cf-date").fill("2027-10-02")
    first.get_by_test_id("cf-save").click()
    expect(first.get_by_test_id("detail-name")).to_have_text(nom)
    expect(competition_card(second, nom)).to_have_count(0)
    _after_next_poll(second_phone, lambda: expect(competition_card(second, nom)).to_be_visible(timeout=POLL_ANSWER_TIMEOUT))


def test_selection_reaches_other_phone(mobile_page, second_phone, test_data):
    member = test_data.competition_group()[0]
    nom = unique_name("E2E Sync")
    test_data.create_competition(nom, date="2027-10-03", participants=[member["id"]])
    first, second = open_screen(mobile_page), open_screen(second_phone)
    open_competition(first, nom)
    open_competition(second, nom)
    participant_card(first, member).get_by_test_id("participe-switch").click()
    expect(participant_card(first, member).get_by_test_id("participe-switch")).to_be_checked()
    switch = participant_card(second, member).get_by_test_id("participe-switch")
    expect(switch).not_to_be_checked()
    _after_next_poll(second_phone, lambda: expect(switch).to_be_checked(timeout=POLL_ANSWER_TIMEOUT))
