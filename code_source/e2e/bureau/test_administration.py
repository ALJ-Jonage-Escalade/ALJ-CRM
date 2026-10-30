"""Office portal, Administration › Accès: an account without access asks for it by signing in, an admin grants it,
the account then opens a coach page. Uses its own account (`applicant`): the access list is shared by every test."""
import pytest
from playwright.sync_api import expect

from helpers.auth import ACCOUNTS, login_as

# Grants a role in the shared access list: never alongside another test of this file
pytestmark = pytest.mark.xdist_group("administration")


def _sign_out(page):
    page.locator("#gate-logout, #logout-btn").first.click()
    expect(page.locator("#gate-login")).to_be_visible()


def test_access_request_granted_then_used(page):
    applicant = ACCOUNTS["applicant"].email

    # 1. Signed in without access: refused, and told the request was sent
    page.goto("/bureau/")
    login_as(page, "applicant")
    expect(page.locator("#gate")).to_contain_text("Accès réservé")
    expect(page.get_by_test_id("gate-request-sent")).to_be_visible()
    _sign_out(page)

    # 2. The admin sees the request and grants it coach
    page.goto("/bureau/administration")
    login_as(page, "admin")
    request = page.get_by_test_id("requests").locator(f'li[data-email="{applicant}"]')
    expect(request).to_be_visible()
    request.get_by_test_id("request-role").select_option("coach")
    request.get_by_test_id("request-grant").click()
    expect(page.get_by_test_id("toast")).to_contain_text(f"Accès Coach donné à {applicant}")
    expect(page.get_by_test_id("access-table").locator(f'tr[data-email="{applicant}"]')).to_be_visible()
    expect(page.get_by_test_id("history")).to_contain_text("Demande acceptée")
    _sign_out(page)

    # 3. The account now opens a coach page
    page.goto("/bureau/planning")
    login_as(page, "applicant")
    expect(page.locator("#who")).to_contain_text("Coach")
    expect(page.locator("#content")).to_be_visible()

