"""Sign-in through the Auth emulator and the office portal gate for each role."""
import re

import pytest
from playwright.sync_api import expect

from helpers.auth import ACCOUNTS
from helpers.stack import AUTH_HOST


def test_emulator_account_picker(page):
    """Real flow: office gate → /competitions?login=1 → emulator picker → back to the office."""
    page.goto("/bureau/")
    page.locator("#gate-login").click()
    page.wait_for_url(re.compile(re.escape(AUTH_HOST) + "/emulator/auth/handler"))
    page.get_by_text(ACCOUNTS["coach"].email).click()
    page.wait_for_url(re.compile(r"/bureau/$"))
    expect(page.locator("#who")).to_contain_text(ACCOUNTS["coach"].email)
    expect(page.locator("#content")).to_be_visible()


@pytest.mark.parametrize("role, label", [("admin", "Administrateur"), ("coach", "Coach")])
def test_staff_sees_office(page, login_as, role, label):
    page.goto("/bureau/")
    login_as(page, role)
    expect(page.locator("#who")).to_contain_text(ACCOUNTS[role].email)
    expect(page.locator("#who")).to_contain_text(label)
    expect(page.locator("#content")).to_be_visible()
    expect(page.locator("#gate")).to_be_hidden()
    # The Google token is not checked in dev mode: no warning (the expired case: frontend AppShell.test.ts)
    expect(page.locator("#google-auth-warning")).to_be_hidden()


@pytest.mark.parametrize("role", ["readonly", "stranger"])
def test_non_staff_is_refused(page, login_as, role):
    page.goto("/bureau/")
    login_as(page, role)
    expect(page.locator("#gate")).to_contain_text("Accès réservé")
    expect(page.locator("#gate-logout")).to_be_visible()
    expect(page.locator("#content")).to_be_hidden()


def test_logout(page, login_as):
    page.goto("/bureau/")
    login_as(page, "admin")
    expect(page.locator("#content")).to_be_visible()
    page.locator("#logout-btn").click()
    expect(page.locator("#gate-login")).to_be_visible()
    expect(page.locator("#login-screen")).to_be_visible()  # full screen, without the menu
    expect(page.locator("#content")).to_be_hidden()


def test_session_survives_reload(page, login_as):
    page.goto("/bureau/")
    login_as(page, "coach")
    expect(page.locator("#content")).to_be_visible()
    page.reload()
    expect(page.locator("#who")).to_contain_text(ACCOUNTS["coach"].email)
