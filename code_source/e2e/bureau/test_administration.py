"""Office portal, Administration › Accès: an account without an invitation is refused, an admin invites it (e-mail in
Mailpit), the account then opens a coach page. Uses its own account (`applicant`): the access list is shared by every
test."""
import pytest
from playwright.sync_api import expect

from helpers.auth import ACCOUNTS, login_as

# Invites into the shared access list: never alongside another test of this file
pytestmark = pytest.mark.xdist_group("administration")


def _sign_out(page):
    page.locator("#gate-logout, #logout-btn").first.click()
    expect(page.locator("#gate-login")).to_be_visible()


def test_invitation_sent_then_used(page, mailpit):
    applicant = ACCOUNTS["applicant"].email

    # 1. Signed in without an invitation: refused, and told to ask for one
    page.goto("/bureau/")
    login_as(page, "applicant")
    expect(page.locator("#gate")).to_contain_text("Accès réservé")
    expect(page.get_by_test_id("gate-not-invited")).to_be_visible()
    _sign_out(page)

    # 2. The admin invites it as coach: the invitation is listed, and its e-mail carries the link
    page.goto("/bureau/administration")
    login_as(page, "admin")
    page.get_by_test_id("access-email").fill(applicant)
    page.get_by_test_id("access-name").fill("Neville")
    page.get_by_test_id("access-role").select_option("coach")
    page.get_by_test_id("access-add").click()
    expect(page.get_by_test_id("toast")).to_contain_text(f"Invitation envoyée à {applicant}")
    row = page.get_by_test_id("access-table").locator(f'tr[data-email="{applicant}"]')
    expect(row.get_by_test_id("entry-status")).to_contain_text("Invité")
    expect(page.get_by_test_id("history")).to_contain_text("Invitation")
    [mail] = mailpit.wait_for(f'to:{applicant} subject:"Invitation au bureau"')
    assert "/bureau/" in mail["Text"]
    assert "en tant que coach" in mail["Text"]
    _sign_out(page)

    # 3. The account now opens a coach page
    page.goto("/bureau/planning")
    login_as(page, "applicant")
    expect(page.locator("#who")).to_contain_text("Coach")
    expect(page.locator("#content")).to_be_visible()
