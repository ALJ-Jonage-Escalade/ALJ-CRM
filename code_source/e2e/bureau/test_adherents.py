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
from helpers.offline import resource_names


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
    # Only the filters are kept (never the search); the Firebase session has its own database. The offline store
    # of the directory and the competitions page only knows its owner here (to be wiped for another account)
    assert people[0]["nom"].lower() not in (stored["local"] + stored["session"]).lower()
    assert resource_names(page) == []


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
    dialog = open_record(page, member)
    expect(dialog.get_by_test_id("record-fields")).to_contain_text(member["email"])
    assert re.search(r"/bureau/adherents\?id=\d+&saison=[\d-]+&achat=\d+$", page.url), page.url
    # The record is in the URL: a reload (or a shared link) opens it again
    page.reload()
    expect(page.get_by_test_id("record-name")).to_have_text(f"{member['prenom']} {member['nom'].upper()}", timeout=20_000)
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("record-dialog")).to_be_hidden()
    assert "id=" not in page.url


def test_former_record_link_opens_the_record(page, people):
    """/bureau/adherents-fiche?id=… (record page of version 2.14) opens the same record."""
    member = people[0]
    open_record(page, member)
    query = page.url.split("?", 1)[1]
    page.goto(f"/bureau/adherents-fiche?{query}")
    page.wait_for_url(re.compile(r"/bureau/adherents\?id="))
    expect(page.get_by_test_id("record-name")).to_have_text(f"{member['prenom']} {member['nom'].upper()}", timeout=20_000)


def test_coach_has_no_admin_action(page):
    open_members(page, role="coach")
    expect(page.get_by_test_id("member-add")).to_have_count(0)
    expect(page.locator("a[href='/bureau/outils?tab=ffme-import']")).to_have_count(0)


def test_coach_record_emails_but_does_not_edit(page, mailpit, people):
    member = people[4]
    accept_dialogs(page)
    dialog = open_record(page, member, role="coach")
    expect(dialog.get_by_test_id("record-readonly")).to_contain_text("réservées aux administrateurs")
    for action in ("record-attestation", "record-edit"):
        expect(dialog.get_by_test_id(action)).to_have_count(0)

    dialog.get_by_test_id("record-email").click()
    topic = unique_name("Coach note")
    dialog.get_by_test_id("email-subject").fill(topic)
    dialog.get_by_test_id("email-body").fill("Hello {first_name}.")
    dialog.get_by_test_id("email-send").click()
    expect(page.get_by_test_id("toast")).to_contain_text("E-mail envoyé avec succès")
    [sent] = mailpit.wait_for(f'to:{member["email"]} subject:"{topic}"')
    assert f"Hello {member['prenom']}." in sent["Text"]


def test_edit_member(page, people):
    member = people[1]
    digits = "06" + str(uuid.uuid4().int)[:8]
    phone = " ".join(digits[i:i + 2] for i in range(0, 10, 2))   # as the server formats it (domain/members/view.py)
    accept_dialogs(page)
    dialog = open_record(page, member)
    dialog.get_by_test_id("record-edit").click()
    dialog.get_by_test_id("member-phone").fill("12")
    dialog.get_by_test_id("member-save").click()
    expect(dialog.get_by_test_id("member-form")).to_contain_text("Numéro de téléphone invalide.")
    dialog.get_by_test_id("member-phone").fill(digits)
    dialog.get_by_test_id("member-badge_rouge").select_option("Oui")
    dialog.get_by_test_id("member-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("mise à jour avec succès")
    expect(dialog.get_by_test_id("record-fields")).to_contain_text(phone)

    # Saved on the server and replicated to Firestore: still there after a reload (the record is in the URL)
    page.reload()
    fields = page.get_by_test_id("record-fields")
    expect(fields).to_contain_text(phone, timeout=20_000)
    expect(fields.get_by_test_id("record-field").filter(has_text="Badge rouge")).to_contain_text("Oui")


def test_edit_without_change(page, people):
    dialog = open_record(page, people[0])
    dialog.get_by_test_id("record-edit").click()
    dialog.get_by_test_id("member-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Aucune modification")
    expect(dialog.get_by_test_id("member-form")).to_be_hidden()
    expect(dialog.get_by_test_id("record-name")).to_be_visible()


def test_add_member(page, test_data):
    # Sorted mid-list: the tests take the first seeded members (people) and Outils the last one
    last_name = unique_name("MEDIANE").upper().replace(" ", "-")
    accept_dialogs(page)
    open_members(page)
    page.get_by_test_id("member-add").click()
    dialog = page.get_by_test_id("add-dialog")
    dialog.get_by_test_id("member-save").click()
    expect(dialog.get_by_test_id("member-last_name")).to_have_attribute("aria-invalid", "true")
    dialog.get_by_test_id("member-last_name").fill(last_name)
    dialog.get_by_test_id("member-first_name").fill("Nina")
    dialog.get_by_test_id("member-birth_date").fill("2012-04-05")
    dialog.get_by_test_id("member-email_primary").fill("nina.e2e@example.org")
    dialog.get_by_test_id("member-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("ajouté avec succès")
    # The new record opens, read from the list reloaded from the server
    expect(page.get_by_test_id("record-name")).to_have_text(f"Nina {last_name}", timeout=20_000)

    page.reload()   # replicated: still there for a new page
    expect(page.get_by_test_id("record-name")).to_have_text(f"Nina {last_name}", timeout=20_000)


def test_send_email(page, mailpit, people):
    member = people[2]
    accept_dialogs(page)
    dialog = open_record(page, member)
    dialog.get_by_test_id("record-email").click()
    expect(dialog.get_by_test_id("email-to")).to_contain_text(member["email"])
    topic = unique_name("Practice moved")
    dialog.get_by_test_id("email-subject").fill(topic + ", {first_name}")
    dialog.get_by_test_id("email-body").fill("Hello {first_name}, practice moves to Thursday.")
    expect(dialog.get_by_test_id("email-preview")).to_contain_text(f"{topic}, {member['prenom']}")
    dialog.get_by_test_id("email-send").click()
    expect(page.get_by_test_id("toast")).to_contain_text("E-mail envoyé avec succès")

    [sent] = mailpit.wait_for(f'to:{member["email"]} subject:"{topic}"')
    assert sent["Subject"] == f"{topic}, {member['prenom']}"
    assert f"Hello {member['prenom']}, practice moves to Thursday." in sent["Text"]


def test_email_needs_subject_and_body(page, people):
    accept_dialogs(page)
    dialog = open_record(page, people[0])
    dialog.get_by_test_id("record-email").click()
    dialog.get_by_test_id("email-send").click()
    expect(dialog.get_by_test_id("email-problem")).to_contain_text("renseigner le sujet et le message")
    expect(dialog.get_by_test_id("email-form")).to_be_visible()


def test_payment_certificate(page, mailpit, people, tmp_path):
    member = people[3]
    accept_dialogs(page)
    dialog = open_record(page, member)
    dialog.get_by_test_id("record-attestation").click()
    # The PDF is generated by the server (WeasyPrint), then shown in the preview frame
    expect(dialog.get_by_test_id("attestation-download")).to_be_enabled(timeout=30_000)
    expect(dialog.get_by_test_id("attestation-pdf")).to_be_visible()
    recipient = dialog.get_by_test_id("attestation-to").input_value()
    assert "@" in recipient

    with page.expect_download() as info:
        dialog.get_by_test_id("attestation-download").click()
    pdf = tmp_path / info.value.suggested_filename
    info.value.save_as(pdf)
    assert re.match(r"Attestation_.+\.pdf$", pdf.name)
    assert pdf.read_bytes().startswith(b"%PDF") and pdf.stat().st_size > 1_000

    dialog.get_by_test_id("attestation-send").click()
    # Sending renders the PDF again (5 s on a loaded CI runner)
    expect(page.get_by_test_id("toast")).to_contain_text("Attestation envoyée avec succès", timeout=30_000)
    [sent] = mailpit.wait_for(f"to:{recipient} has:attachment")   # the only e-mails with one
    attachments = sent["Attachments"]
    assert [a["ContentType"] for a in attachments] == ["application/pdf"]
    assert attachments[0]["FileName"].endswith(".pdf")
    # The sent date is recorded and shown once the list is reloaded
    expect(dialog.get_by_test_id("record-fields")).to_contain_text("Attestation envoyée", timeout=20_000)
