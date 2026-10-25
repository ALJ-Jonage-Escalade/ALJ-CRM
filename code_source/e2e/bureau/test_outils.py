"""Office portal, Outils page (Vue app): members map, pivot table, attendance sheets, FFME export and import;
Google token warning of every office page."""
import csv
import io
import json
import zipfile

import openpyxl
import pytest

from playwright.sync_api import expect

from helpers.auth import login_as
from helpers.data import eventually
from helpers.dialogs import confirm_dialog

# Attendance sheets and exports list the planning slots, which test_planning.py creates and deletes
pytestmark = pytest.mark.xdist_group("planning")


def _open(page, role="admin", tab=None):
    page.goto("/bureau/outils" + (f"?tab={tab}" if tab else ""))
    login_as(page, role)
    if tab:
        expect(page.get_by_test_id(f"pane-{tab}")).to_be_visible()
    return page


def _saved(download, folder):
    target = folder / download.suggested_filename
    download.save_as(target)
    return target


def test_members_map(page):
    """Map of the members' addresses (Leaflet). The e2e setup pre-fills the geocache, so the
    server never calls Nominatim."""
    _open(page)
    expect(page.get_by_test_id("map-stats")).to_contain_text("réparti", timeout=30_000)
    expect(page.get_by_test_id("map-view").locator(".leaflet-tile-pane")).to_be_attached()
    # Members are shown as markers grouped in clusters; a cluster zooms in down to the markers, a marker opens its popup
    clusters = page.get_by_test_id("map-view").locator(".marker-cluster, .leaflet-marker-icon")
    expect(clusters.first).to_be_visible(timeout=15_000)
    for _ in range(10):
        if page.get_by_test_id("map-popup").count():
            break
        markers = page.get_by_test_id("map-view").locator(".leaflet-marker-icon:not(.marker-cluster)")
        (markers if markers.count() else clusters).first.click()
        page.wait_for_timeout(500)
    expect(page.get_by_test_id("map-popup")).to_contain_text("Adhérent")

    # Group filter: hiding every group empties the map
    page.get_by_test_id("map-groups").click()
    page.get_by_test_id("map-group-all").uncheck()
    expect(page.get_by_test_id("map-stats")).to_contain_text("0 adhérent réparti sur 0 adresse")
    expect(page.get_by_test_id("map-groups")).to_contain_text("Aucun groupe sélectionné")
    page.keyboard.press("Escape")

    page.get_by_test_id("tools-refresh").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Carte réactualisée")


def test_pivot_table_by_season(page):
    _open(page)
    page.get_by_test_id("tab-pivot").click()
    page.wait_for_url("**/bureau/outils?tab=pivot")
    expect(page.get_by_test_id("pivot-frame")).to_be_visible(timeout=30_000)
    seasons = page.get_by_test_id("pivot-season").locator("option")
    expect(seasons).to_have_count(3)  # the two seeded seasons + all seasons
    frame = page.frame_locator("[data-testid=pivot-frame]")
    expect(frame.locator(".pvtTable, .pvtUi").first).to_be_visible(timeout=15_000)

    with page.expect_response(lambda r: "/pivot?season=2025-2026" in r.url and r.ok):
        page.get_by_test_id("pivot-season").select_option("2025-2026")
    expect(frame.locator(".pvtTable, .pvtUi").first).to_be_visible()
    with page.expect_response(lambda r: "/pivot?season=Toutes%20les%20saisons" in r.url and r.ok):
        page.get_by_test_id("pivot-season").select_option("Toutes les saisons")
    expect(frame.locator(".pvtTable, .pvtUi").first).to_be_visible()


def test_expired_google_token_warning(page):
    """Every office page warns when the club's Google token has expired."""
    page.route("**/api/auth/google/status", lambda route: route.fulfill(
        content_type="application/json", body=json.dumps({"status": "expired", "user_email": "office@hogwarts.example"})))
    page.goto("/bureau/")
    login_as(page, "admin")
    expect(page.locator("#google-auth-warning")).to_be_visible()


# ---------------------------------------------------------------------------
# Attendance sheets and FFME licences
# ---------------------------------------------------------------------------
def test_course_attendance_sheets(page, tmp_path):
    config = page.request.get("/api/presence/config").json()
    courses = config["cours"]
    assert courses, "the seed plans supervised courses"
    _open(page, "coach", "presence")
    expect(page.get_by_test_id("course-count")).to_have_text(f"{len(courses)} créneau(x)")
    expect(page.get_by_test_id("course")).to_have_count(len(courses))
    expect(page.get_by_test_id("courses-start")).to_have_value(config["default_dates"]["start"])

    page.get_by_test_id("courses-none").click()
    page.get_by_test_id("download-courses").click()
    expect(page.get_by_test_id("toast")).to_contain_text("cocher au moins un groupe")

    # One workbook, one sheet page per course
    page.get_by_test_id("courses-all").click()
    with page.expect_download() as info:
        page.get_by_test_id("download-courses").click()
    workbook = openpyxl.load_workbook(_saved(info.value, tmp_path))
    text = " ".join(str(c) for ws in workbook.worksheets for row in ws.iter_rows(values_only=True) for c in row if c)
    assert all(course["groupe"] in text for course in courses)

    # One file per course, in a ZIP archive
    page.get_by_test_id("courses-zip").check()
    with page.expect_download() as info:
        page.get_by_test_id("download-courses").click()
    with zipfile.ZipFile(_saved(info.value, tmp_path)) as archive:
        names = archive.namelist()
    assert len(names) == len(courses) and all(n.endswith(".xlsx") for n in names)


def test_autonomous_attendance_sheet(page, tmp_path):
    _open(page, "admin", "presence")
    expect(page.get_by_test_id("presence-autonomous-summary")).to_contain_text("Total adhérents")
    expect(page.get_by_test_id("presence-autonomous-summary")).not_to_contain_text("Total adhérents : 0")
    with page.expect_download() as info:
        page.get_by_test_id("download-autonomous").click()
    assert _saved(info.value, tmp_path).stat().st_size > 0


def test_ffme_licences_export(page, tmp_path):
    stats = page.request.get("/api/ffme/stats").json()
    _open(page, "coach", "ffme")
    expect(page.get_by_test_id("ffme-total")).to_have_text(str(stats["estimated_total"]))
    expect(page.get_by_test_id("ffme-renewals")).to_have_text(str(stats["renewals_count"]))
    expect(page.get_by_test_id("ffme-new")).to_have_text(str(stats["new_licences_count"]))
    assert stats["renewals_count"] + stats["new_licences_count"] == stats["estimated_total"]

    with page.expect_download() as info:
        page.get_by_test_id("ffme-download").click()
    assert info.value.suggested_filename.startswith("import_ffme_")
    text = _saved(info.value, tmp_path).read_text(encoding="utf-8-sig")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert rows[0][:3] == ["numero de licence", "nom", "prenom"]
    assert len([r for r in rows[1:] if r]) == stats["estimated_total"]

    page.get_by_test_id("ffme-include-finished").uncheck()
    with page.expect_response(lambda r: "include_termine=false" in r.url and r.ok), page.expect_download():
        page.get_by_test_id("ffme-download").click()


def test_coach_has_no_ffme_import(page):
    _open(page, "coach")
    page.goto("/bureau/outils?tab=ffme-import")
    expect(page.get_by_test_id("tab-ffme")).to_be_visible()
    expect(page.get_by_test_id("tab-ffme-import")).to_have_count(0)
    expect(page.get_by_test_id("pane-ffme-import")).to_have_count(0)


def _ffme_file(folder, rows):
    """A MyFFME export: a title row, then the header."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Liste des licenciés"])
    header = ["Nom", "Prénom", "N° de licence", "Date de naissance", "Passeports", "Diplômes", "Document de santé"]
    ws.append(header)
    for row in rows:
        ws.append([row.get(h, "") for h in header])
    path = folder / "licencies_ffme.xlsx"
    wb.save(path)
    return path


def test_ffme_import_preview_and_apply(page, test_data, tmp_path):
    """The last seeded member (test_adherents.py changes the first ones) is matched by name; the unknown row is left out."""
    member = sorted(test_data.members(), key=lambda m: (m["nom"], m["prenom"]))[-1]
    path = _ffme_file(tmp_path, [
        {"Nom": member["nom"], "Prénom": member["prenom"], "N° de licence": "4242420", "Passeports": "Passeport Blanc"},
        {"Nom": "INCONNU", "Prénom": "Zoé", "N° de licence": "9999999", "Date de naissance": "01/02/2010"},
    ])
    _open(page, "admin", "ffme-import")
    expect(page.get_by_test_id("ffme-analyze")).to_be_disabled()
    page.get_by_test_id("ffme-file").set_input_files(path)
    expect(page.get_by_test_id("ffme-file-name")).to_contain_text("licencies_ffme.xlsx")

    page.get_by_test_id("ffme-analyze").click()
    expect(page.get_by_test_id("ffme-rows")).to_have_text("2")
    expect(page.get_by_test_id("ffme-by-name")).to_have_text("1")
    expect(page.get_by_test_id("ffme-unmatched")).to_have_count(1)
    expect(page.get_by_test_id("ffme-unmatched")).to_contain_text("INCONNU Zoé")
    expect(page.get_by_test_id("ffme-match").locator("option:checked")).to_have_text("-- Ignorer cette ligne --")

    page.get_by_test_id("ffme-apply").click()
    confirm_dialog(page)
    expect(page.get_by_test_id("ffme-import-done")).to_contain_text("1 adhérents ont été mis à jour")
    expect(page.get_by_test_id("toast")).to_contain_text("Importation FFME validée : 1 adhérents mis à jour.")

    def licence():
        found = next(m for m in test_data.members() if m["id"] == member["id"])
        assert found.get("licence_ffme") == "4242420"
    eventually(licence, timeout=15)
