"""Office portal, planning page: week view, table and filters, slot create/edit/delete, print, Excel exports."""
import io

import openpyxl
import pytest
from playwright.sync_api import expect

from helpers.auth import login_as
from helpers.competitions import sub_menu_entry
from helpers.data import unique_name
from helpers.dialogs import cancel_dialog, confirm_dialog

# Tests create slots and compare counts with /api/planning: one after another, with test_outils.py
pytestmark = pytest.mark.xdist_group("planning")
DAYS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi")


@pytest.fixture
def planning(page):
    """Seeded slots (from the API) and cleanup of the slots a test creates: other tests read the planning."""
    before = {s["id"]: s for s in page.request.get("/api/planning").json()}
    yield list(before.values())
    for slot in page.request.get("/api/planning").json():
        if slot["id"] not in before:
            page.request.delete(f"/api/planning/item/{slot['id']}")
        elif slot != before[slot["id"]]:
            page.request.post("/api/planning/item", data=before[slot["id"]])


def _open(page, role="admin"):
    page.goto("/bureau/planning")
    login_as(page, role)
    expect(page.get_by_test_id("slot-count")).to_contain_text("configuré", timeout=20_000)
    return page


def _row(page, groupe):
    return page.get_by_test_id("slot-row").filter(has=page.get_by_text(groupe, exact=True))


def _stored(page, groupe):
    return next(s for s in page.request.get("/api/planning").json() if s["groupe"] == groupe)


def _xlsx_text(download, folder) -> str:
    target = folder / download.suggested_filename
    download.save_as(target)
    book = openpyxl.load_workbook(io.BytesIO(target.read_bytes()))
    return " ".join(str(c) for ws in book.worksheets for row in ws.iter_rows(values_only=True) for c in row if c)


def test_week_view_and_table(page, planning):
    _open(page)
    expect(page.get_by_test_id("slot-count")).to_have_text(f"{len(planning)} créneaux configurés")
    # One card per slot of a single day (the « Lundi / Jeudi » slot spans two days: not on the grid)
    on_grid = [s for s in planning if s["jour"] in DAYS]
    expect(page.get_by_test_id("slot-card")).to_have_count(len(on_grid))
    saturday = next(s for s in planning if s["jour"] == "Samedi")
    expect(page.get_by_test_id("day-Samedi").get_by_test_id("slot-card")).to_contain_text(saturday["groupe"])

    sub_menu_entry(page, "tableau").click()
    expect(page.get_by_test_id("slot-row")).to_have_count(len(planning))
    page.get_by_test_id("slot-search").fill("bouldering")
    expect(page.get_by_test_id("slot-row")).to_have_count(1)
    page.get_by_test_id("slot-search").fill("")
    page.get_by_test_id("kind-compétition").click()
    competition = [s for s in planning if s["type"] == "compétition"]
    expect(page.get_by_test_id("slot-row")).to_have_count(len(competition))
    page.get_by_test_id("kind-all").click()
    expect(page.get_by_test_id("slot-row")).to_have_count(len(planning))


def test_create_edit_delete_slot(page, planning):
    groupe = unique_name("E2E Slot")
    _open(page)
    page.get_by_test_id("slot-new").click()
    expect(page.get_by_test_id("slot-dialog")).to_be_visible()
    page.get_by_test_id("slot-groupe").fill(groupe)
    page.get_by_test_id("slot-jour").select_option("Samedi")
    page.get_by_test_id("slot-horaires").fill("14:00 - 16:00")
    page.get_by_test_id("slot-type").select_option("perfectionnement")
    page.get_by_test_id("slot-categorie").fill("U14-U16")
    page.get_by_test_id("slot-encadrants").fill("Remus Lupin, Rubeus Hagrid")
    page.get_by_test_id("slot-whatsapp").fill("https://chat.whatsapp.com/e2e")
    page.get_by_test_id("slot-tarifs").locator("label").filter(has_text="Autonome bouldering").locator("input").check()
    page.get_by_test_id("slot-naissance-min").fill("2010")
    page.get_by_test_id("slot-naissance-max").fill("2012")
    page.get_by_test_id("slot-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text(f"Créneau « {groupe} » enregistré")
    expect(page.get_by_test_id("slot-dialog")).to_be_hidden()
    expect(page.get_by_test_id("day-Samedi").get_by_test_id("slot-card").filter(has_text=groupe)).to_be_visible()

    sub_menu_entry(page, "tableau").click()
    row = _row(page, groupe)
    expect(row).to_contain_text("Remus Lupin, Rubeus Hagrid")
    expect(row).to_contain_text("Autonome bouldering")
    expect(row).to_contain_text("Nés entre 2010 et 2012")
    stored = _stored(page, groupe)
    assert {k: stored[k] for k in ("jour", "horaires", "type", "categorie_age", "whatsapp_link", "naissance_min", "naissance_max")} == {
        "jour": "Samedi", "horaires": "14:00 - 16:00", "type": "perfectionnement", "categorie_age": "U14-U16",
        "whatsapp_link": "https://chat.whatsapp.com/e2e", "naissance_min": "2010", "naissance_max": "2012"}
    assert (stored["encadrants"], stored["helloasso_tarifs"]) == (["Remus Lupin", "Rubeus Hagrid"], ["Autonome bouldering"])

    # Editing changes the hours and keeps every other field
    row.get_by_test_id("slot-edit").click()
    expect(page.get_by_test_id("slot-groupe")).to_have_value(groupe)
    expect(page.get_by_test_id("slot-tarifs").locator("label").filter(has_text="Autonome bouldering").locator("input")).to_be_checked()
    page.get_by_test_id("slot-horaires").fill("16:00 - 18:00")
    page.get_by_test_id("slot-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("enregistré")
    sub_menu_entry(page, "tableau").click()
    expect(_row(page, groupe)).to_contain_text("16:00 - 18:00")
    assert _stored(page, groupe) == {**stored, "horaires": "16:00 - 18:00"}

    # The week view's card opens the same form
    sub_menu_entry(page, "semaine").click()
    page.get_by_test_id("slot-card").filter(has_text=groupe).click()
    expect(page.get_by_test_id("slot-groupe")).to_have_value(groupe)
    page.get_by_test_id("slot-cancel").click()
    expect(page.get_by_test_id("slot-dialog")).to_be_hidden()

    sub_menu_entry(page, "tableau").click()
    _row(page, groupe).get_by_test_id("slot-delete").click()
    cancel_dialog(page)
    expect(_row(page, groupe)).to_have_count(1)
    _row(page, groupe).get_by_test_id("slot-delete").click()
    confirm_dialog(page)
    expect(page.get_by_test_id("toast")).to_contain_text("Créneau supprimé")
    expect(_row(page, groupe)).to_have_count(0)
    assert all(s["groupe"] != groupe for s in page.request.get("/api/planning").json())


def test_editing_keeps_a_two_day_slot(page, planning):
    """Its day is not in the form's list: saving keeps it (the former page moved the slot to Monday)."""
    two_days = next(s for s in planning if s["jour"] == "Lundi / Jeudi")
    _open(page)
    sub_menu_entry(page, "tableau").click()
    _row(page, two_days["groupe"]).get_by_test_id("slot-edit").click()
    page.get_by_test_id("slot-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("enregistré")
    assert _stored(page, two_days["groupe"])["jour"] == "Lundi / Jeudi"


@pytest.mark.xfail(strict=True, reason="the week view has no Sunday column (like the Excel grid) "
                                       "although the slot form offers « Dimanche »")
def test_sunday_slot_on_week_view(page, planning):
    groupe = unique_name("E2E Sunday")
    _open(page)
    page.get_by_test_id("slot-new").click()
    page.get_by_test_id("slot-groupe").fill(groupe)
    page.get_by_test_id("slot-jour").select_option("Dimanche")
    page.get_by_test_id("slot-horaires").fill("10:00 - 12:00")
    page.get_by_test_id("slot-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("enregistré")
    expect(page.get_by_test_id("slot-card").filter(has_text=groupe)).to_be_visible()


@pytest.mark.parametrize("field", ["slot-groupe", "slot-horaires"])
def test_name_and_hours_are_required(page, planning, field):
    _open(page)
    page.get_by_test_id("slot-new").click()
    page.get_by_test_id("slot-groupe").fill(unique_name("E2E Required"))
    page.get_by_test_id(field).fill("")
    page.get_by_test_id("slot-save").click()
    expect(page.get_by_test_id("slot-dialog")).to_be_visible()
    assert len(page.request.get("/api/planning").json()) == len(planning)


def test_excel_exports(page, planning, tmp_path):
    _open(page)
    for button, title in (("export-grid", "Saison"), ("export-list", "Groupe")):
        page.get_by_test_id("export-menu").click()
        with page.expect_download() as info:
            page.get_by_test_id(button).click()
        assert info.value.suggested_filename.endswith(".xlsx")
        text = _xlsx_text(info.value, tmp_path)
        assert title in text
        assert all(slot["groupe"] in text for slot in planning), f"{button}: a slot is missing"


def test_print_shows_the_grid_only(page, planning):
    _open(page)
    page.emulate_media(media="print")
    expect(page.get_by_test_id("day-Samedi")).to_be_visible()
    for control in ("slot-new", "planning-print", "export-menu", "subnav-side", "subnav-strip"):
        expect(page.get_by_test_id(control)).to_be_hidden()


def test_phone(mobile_page, planning):
    """Read and edit on a phone: no horizontal page scroll, the form fits the screen."""
    page = _open(mobile_page)
    assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
    sub_menu_entry(page, "tableau").click()
    expect(page.get_by_test_id("slot-row")).to_have_count(len(planning))
    assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
    _row(page, planning[0]["groupe"]).get_by_test_id("slot-edit").click()
    box = page.get_by_test_id("slot-dialog").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"]
    expect(page.get_by_test_id("slot-save")).to_be_visible()


def test_coach_changes_a_slot(page, planning):
    """Coaches change the slots too (only replacing the whole planning is for admins)."""
    saturday = next(s for s in planning if s["jour"] == "Samedi")
    _open(page, "coach")
    page.get_by_test_id("day-Samedi").get_by_test_id("slot-card").first.click()
    page.get_by_test_id("slot-encadrants").fill("Remus Lupin")
    page.get_by_test_id("slot-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text(f"Créneau « {saturday['groupe']} » enregistré")
    assert _stored(page, saturday["groupe"])["encadrants"] == ["Remus Lupin"]  # the fixture puts the slot back
