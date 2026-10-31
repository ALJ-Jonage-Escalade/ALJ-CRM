"""Office portal, Outils › Import HelloAsso: the membership campaign of the (fake) HelloAsso imported as members, with
a preview, per-row checkboxes, a row to review and the result screen (frontend/src/pages/outils/HelloAssoImportPane.vue).

Only people made up by the test are written: a first import creates one of them (another is left unchecked), a second
one brings a renewal and an ambiguous registration of that same person, linked to them by hand."""
import uuid

import pytest
from playwright.sync_api import expect

from helpers import helloasso
from helpers.auth import login_as
from helpers.dialogs import confirm_dialog
from helpers.members import ROWS, open_members

# One fake HelloAsso state for the whole server: these tests run one after another (conftest.py)
pytestmark = pytest.mark.xdist_group("helloasso")


def _open(page):
    page.goto("/bureau/outils/helloasso-import")
    login_as(page, "admin")
    expect(page.get_by_test_id("ha-last-sync")).to_be_visible()


def _preview(page):
    page.get_by_test_id("ha-import-preview").click()
    expect(page.get_by_test_id("ha-import-campaign")).to_contain_text(helloasso.MEMBERSHIP_FORM, timeout=20_000)


def _row(page, bucket: str, text: str):
    return page.get_by_test_id(f"ha-row-{bucket}").filter(has_text=text)


def _import(page):
    page.get_by_test_id("ha-import-apply").click()
    confirm_dialog(page)
    expect(page.get_by_test_id("ha-import-done")).to_be_visible(timeout=20_000)


def test_import_from_the_membership_campaign(page, fake_helloasso):
    tag = uuid.uuid4().hex[:6]
    joined, left_out = f"Rusard{tag}", f"Trelawney{tag}"
    first_run = [helloasso.membership_item("Argus", joined, "12/03/1990"),
                 helloasso.membership_item("Sibylle", left_out, "09/03/1985")]
    fake_helloasso.set(first_run)

    _open(page)
    _preview(page)
    expect(_row(page, "new", joined)).to_be_visible()
    _row(page, "new", left_out).get_by_test_id("ha-check").uncheck()
    expect(page.get_by_test_id("ha-import-selected")).to_contain_text("1 inscription")
    _import(page)
    expect(page.get_by_test_id("ha-created")).to_have_count(1)
    expect(page.get_by_test_id("ha-created")).to_contain_text(joined)
    expect(page.get_by_test_id("ha-last-sync")).to_contain_text("Dernière synchro")

    # Second run: the imported registration is known; a new registration of the same person is a renewal, one with
    # another birth date is left to the admin, who links it to that person
    renewal = helloasso.membership_item("Argus", joined, "12/03/1990", tariff="Adultes loisir")
    ambiguous = helloasso.membership_item("Argus", joined, "21/03/1990", tariff="Adultes loisir")
    fake_helloasso.set(first_run + [renewal, ambiguous])
    _preview(page)
    expect(_row(page, "already_imported", joined)).to_have_count(1)
    expect(_row(page, "new", left_out)).to_be_visible()
    _row(page, "new", left_out).get_by_test_id("ha-check").uncheck()
    expect(_row(page, "renewal", joined)).to_have_count(1)
    review = _row(page, "to_review", joined)
    expect(review).to_contain_text("date de naissance différente")
    choice = review.get_by_test_id("ha-review-choice")
    expect(choice).to_have_value("skip")
    choice.select_option(index=1)  # the candidate: the member created by the first run
    _import(page)
    expect(page.get_by_test_id("ha-renewed")).to_have_count(2)
    expect(page.get_by_test_id("ha-created")).to_have_count(0)

    # The imported member is in Adhérents; the unchecked registration is not
    open_members(page)
    page.get_by_test_id("member-search").fill(joined)
    expect(page.get_by_test_id(ROWS)).to_have_count(3)  # one row per membership of the season
    page.get_by_test_id("member-search").fill(left_out)
    expect(page.get_by_test_id(ROWS)).to_have_count(0)
