"""Office portal, members: the list (Vue app: filters, sort, CSV export, polling) and the member record (former page
until plan phase 8: edit, e-mail, payment certificate), opened from the list."""
import csv
import io
import re
import uuid

import pytest
from playwright.sync_api import expect

from helpers.auth import login_as
from helpers.data import unique_name
from helpers.members import ROWS, displayed_count, find, open_members, open_record
from helpers.mobile import accept_dialogs


@pytest.fixture(scope="module")
def people(test_data):
    """Seeded members of the active season, one per test that sends or changes something."""
    found = sorted(test_data.members(), key=lambda m: (m["nom"], m["prenom"]))
    assert len(found) >= 6
    return found


def test_list_search(page, people):
    member = people[0]
    open_members(page)
    total = displayed_count(page)
    assert total > 20
    expect(page.get_by_test_id(ROWS)).to_have_count(min(total, 50))

    row = find(page, member)
    expect(row).to_have_count(1)
    expect(row).to_contain_text(member["email"])
    if member.get("licence_ffme"):
        expect(row).to_contain_text(member["licence_ffme"])
    assert displayed_count(page) < total
    page.get_by_test_id("member-search").fill("")
    expect(page.get_by_test_id("member-count")).to_contain_text(f"{total} adhérent")


def test_season_switch(page):
    open_members(page)
    current = displayed_count(page)
    select = page.get_by_test_id("season-select")
    seasons = select.locator("option")
    expect(seasons).to_have_count(2)
    previous = seasons.nth(1).get_attribute("value")
    select.select_option(previous)
    expect(page.get_by_test_id("member-count")).to_contain_text(f"(saison {previous})")
    assert displayed_count(page) != current, "the seed re-registers only part of the members"


def test_slot_filters(page):
    open_members(page)
    total = displayed_count(page)
    page.get_by_test_id("filter-toggle").click()
    expect(page.get_by_test_id("filter-box")).to_be_visible()
    page.get_by_test_id("filter-none").click()
    expect(page.get_by_test_id("data-empty")).to_contain_text("Aucun adhérent ne correspond")
    page.get_by_test_id("filter-all").click()
    assert displayed_count(page) >= total

    slot = page.get_by_test_id("filter-group").first
    in_slot = int(slot.get_by_test_id("filter-count").inner_text())
    before = displayed_count(page)
    slot.locator("input").uncheck()
    expect(page.get_by_test_id("member-count")).to_contain_text(f"{before - in_slot} adhérent")


def test_status_filter(page):
    open_members(page)
    chip = page.locator("[data-testid^='status-']:not([data-testid='status-all'])").first
    count = int(re.search(r"\((\d+)\)", chip.inner_text()).group(1))
    chip.click()
    expect(page.get_by_test_id("member-count")).to_contain_text(f"{count} adhérent")


def test_sort_by_last_name(page):
    open_members(page)
    names = lambda: [r.split("\t")[0] for r in page.get_by_test_id(ROWS).all_inner_texts()]  # noqa: E731
    ascending = names()
    assert ascending == sorted(ascending, key=str.lower)
    page.get_by_test_id("sort-last_name").click()
    expect(page.locator("th[aria-sort='descending']")).to_have_count(1)
    descending = names()
    assert descending == sorted(descending, key=str.lower, reverse=True)
    assert descending[0] >= ascending[-1]


def test_pages(page):
    open_members(page)
    if displayed_count(page) <= 50:
        pytest.skip("the seed fits on one page")
    first = page.get_by_test_id(ROWS).first.inner_text()
    page.get_by_test_id("pager-next").click()
    expect(page.get_by_test_id("pager-range")).to_contain_text("51–")
    expect(page.get_by_test_id(ROWS).first).not_to_have_text(first)


def test_csv_export(page, tmp_path):
    open_members(page)
    total = displayed_count(page)
    with page.expect_download() as info:
        page.get_by_test_id("export-csv").click()
    target = tmp_path / info.value.suggested_filename
    info.value.save_as(target)
    assert re.fullmatch(r"adherents_\d{4}-\d{4}\.csv", target.name)
    rows = list(csv.reader(io.StringIO(target.read_text(encoding="utf-8-sig")), delimiter=";"))
    assert rows[0][:3] == ["Nom", "Prénom", "Date de naissance"]
    assert len(rows) == 1 + total   # every page, not only the one shown
    # Spreadsheet formula injection neutralised (frontend/src/lib/csv.ts): only phone/signed numbers
    # may start with + or -, nothing may start with = or @
    risky = [c for row in rows[1:] for c in row if c[:1] in ("=", "+", "-", "@")]
    assert all(re.fullmatch(r"[+-][\d\s().,]*", c) for c in risky), risky
    assert any(c.startswith("+") for c in risky), "seeded phone numbers are exported as is"


def test_list_refreshes_while_open(page, people):
    """Polled through the API: an unchanged poll is a 304, a change shows without reloading the page."""
    member = people[5]
    open_members(page)
    with page.expect_response(lambda r: r.url.endswith("/api/members") and r.status == 304):
        page.evaluate("window.dispatchEvent(new Event('online'))")   # reloads now instead of in 20 s

    note = unique_name("refreshed")
    page.get_by_test_id("member-search").fill(note)
    expect(page.get_by_test_id("data-empty")).to_be_visible()
    listed = next(m for m in page.request.get("/api/members").json()["members"]
                  if m["last_name"] == member["nom"].upper() and m["first_name"] == member["prenom"])
    answer = page.request.post("/api/members/update", data={"purchase_id": listed["purchase_id"],
                                                            "fields": {"commentaires_correctif": note}})
    assert answer.ok, answer.text()
    with page.expect_response(lambda r: r.url.endswith("/api/members") and r.status == 200):
        page.evaluate("window.dispatchEvent(new Event('online'))")
    expect(page.get_by_test_id(ROWS)).to_have_count(1)
    expect(page.get_by_test_id(ROWS)).to_contain_text(member["nom"].upper())


def test_nothing_stored_on_the_device(page, people):
    open_members(page)
    expect(find(page, people[0])).to_have_count(1)
    stored = page.evaluate("""async () => ({
        local: Object.keys(localStorage).map(k => k + "=" + localStorage.getItem(k)).join("\\n"),
        session: Object.keys(sessionStorage).map(k => k + "=" + sessionStorage.getItem(k)).join("\\n"),
        databases: (await indexedDB.databases()).map(d => d.name),
    })""")
    # Only the filters are kept (never the search); the Firebase session has its own database
    assert people[0]["nom"].lower() not in (stored["local"] + stored["session"]).lower()
    assert "alj-offline" not in stored["databases"]


def test_phone_shows_stacked_cards(mobile_page, people):
    page = mobile_page
    page.goto("/bureau/adherents")
    login_as(page, "admin")
    card = page.get_by_test_id("data-card").first
    expect(card).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("data-table")).to_be_hidden()
    page.get_by_test_id("member-search").fill(people[0]["nom"])
    expect(page.get_by_test_id("data-card").filter(has_text=people[0]["prenom"])).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no horizontal scroll"


def test_record_opens_from_the_list(page, people):
    member = people[0]
    pane = open_record(page, member)
    expect(pane).to_contain_text(member["email"])
    page.get_by_test_id("back-to-list").click()
    expect(page.get_by_test_id(ROWS).first).to_be_visible(timeout=20_000)


def test_add_member_link(page):
    open_members(page)
    page.get_by_test_id("member-add").click()
    expect(page.locator("#member-add-modal")).to_be_visible(timeout=20_000)


def test_coach_has_no_admin_action(page):
    open_members(page, role="coach")
    expect(page.get_by_test_id("member-add")).to_have_count(0)
    expect(page.locator("a[href='/bureau/outils?tab=ffme-import']")).to_have_count(0)


def test_edit_member(page, people):
    member = people[1]
    digits = "06" + str(uuid.uuid4().int)[:8]
    phone = " ".join(digits[i:i + 2] for i in range(0, 10, 2))   # as fmtPhone (alj-members.js) shows it
    accept_dialogs(page)
    open_record(page, member).locator("#btn-action-edit").click()
    expect(page.locator("#member-edit-modal")).to_be_visible()
    page.locator("#edit-phone").fill(digits)
    page.locator("#edit-badge-rouge").select_option("Oui")
    page.locator("#edit-save-btn").click()
    expect(page.locator("#toast")).to_contain_text("mise à jour avec succès")
    expect(page.locator("#detail-pane")).to_contain_text(phone)

    # Saved on the server and replicated to Firestore: still there after a reload (the record opens on ?id=)
    page.reload()
    pane = page.locator("#detail-pane")
    expect(pane).to_contain_text(phone, timeout=20_000)
    expect(pane.locator("tr").filter(has_text="Badge rouge")).to_contain_text("Oui")


def test_edit_without_change(page, people):
    open_record(page, people[0]).locator("#btn-action-edit").click()
    page.locator("#edit-save-btn").click()
    expect(page.locator("#toast")).to_contain_text("Aucune modification")
    expect(page.locator("#member-edit-modal")).to_be_hidden()


def test_send_email(page, mailpit, people):
    member = people[2]
    accept_dialogs(page)
    open_record(page, member).locator("#btn-action-email").click()
    expect(page.locator("#em-dest-email")).to_contain_text(member["email"])
    topic = unique_name("Practice moved")
    page.locator("#em-subject").fill(topic + ", {first_name}")
    page.locator("#em-body").fill("Hello {first_name}, practice moves to Thursday.")
    expect(page.locator("#em-preview-box")).to_contain_text(f"{topic}, {member['prenom']}")
    page.locator("#em-submit-btn").click()
    expect(page.locator("#toast")).to_contain_text("E-mail envoyé avec succès")

    [sent] = mailpit.wait_for(f'to:{member["email"]} subject:"{topic}"')
    assert sent["Subject"] == f"{topic}, {member['prenom']}"
    assert f"Hello {member['prenom']}, practice moves to Thursday." in sent["Text"]


def test_email_needs_subject_and_body(page, people):
    accept_dialogs(page)
    open_record(page, people[0]).locator("#btn-action-email").click()
    page.locator("#em-submit-btn").click()
    expect(page.locator("#toast")).to_contain_text("renseigner le sujet et le message")
    expect(page.locator("#email-modal")).to_be_visible()


def test_payment_certificate(page, mailpit, people, tmp_path):
    member = people[3]
    accept_dialogs(page)
    open_record(page, member).locator("#btn-action-attestation").click()
    expect(page.locator("#attestation-modal")).to_be_visible()
    # The PDF is generated by the server (WeasyPrint), then shown in the preview frame
    expect(page.locator("#att-download-btn")).to_be_enabled(timeout=30_000)
    expect(page.locator("#att-pdf-frame")).to_be_visible()
    recipient = page.locator("#att-to-email").input_value()
    assert "@" in recipient

    with page.expect_download() as info:
        page.locator("#att-download-btn").click()
    pdf = tmp_path / info.value.suggested_filename
    info.value.save_as(pdf)
    assert re.match(r"Attestation_.+\.pdf$", pdf.name)
    assert pdf.read_bytes().startswith(b"%PDF") and pdf.stat().st_size > 1_000

    page.locator("#att-send-btn").click()
    # Sending renders the PDF again (5 s on a loaded CI runner)
    expect(page.locator("#toast")).to_contain_text("Attestation envoyée avec succès", timeout=30_000)
    [sent] = mailpit.wait_for(f"to:{recipient} has:attachment")   # the only e-mails with one
    attachments = sent["Attachments"]
    assert [a["ContentType"] for a in attachments] == ["application/pdf"]
    assert attachments[0]["FileName"].endswith(".pdf")
    expect(page.locator("#detail-pane")).to_contain_text("Attestation envoyée")


def test_coach_record_is_consultation_only(page, people):
    pane = open_record(page, people[0], role="coach")
    expect(pane).to_contain_text("Mode consultation coach")
    for action in ("#btn-action-email", "#btn-action-attestation", "#btn-action-edit"):
        expect(pane.locator(action)).to_have_count(0)
