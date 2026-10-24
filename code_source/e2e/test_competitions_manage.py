"""Competitions screen, coaches and admins: create, edit, delete and archive competitions, search and date filters,
spreadsheet export (frontend/src/pages/CompetitionsPage.vue, plan phase 11), on a phone and on desktop."""
import csv
import datetime
import io
import re

import pytest
from playwright.sync_api import expect

from helpers.competitions import SEEDED_COMPETITION, archived_card, competition_card, open_competition, open_screen, toast
from helpers.data import eventually, unique_name
from helpers.dialogs import accept_dialogs


def _iso(days: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def tick_coach(page, nom: str) -> None:
    page.get_by_test_id("cf-coaches").locator("label").filter(has_text=nom).locator("input").check()


def test_create_competition(mobile_page, test_data):
    page = open_screen(mobile_page)
    nom = unique_name("E2E Create")
    page.get_by_test_id("create-comp").click()
    page.get_by_test_id("cf-nom").fill(nom)
    page.get_by_test_id("cf-idffme").fill("EVT-E2E-1")
    page.get_by_test_id("cf-date").fill("2027-03-14")
    page.get_by_test_id("cf-date-fin").fill("2027-03-15")
    page.get_by_test_id("cf-lieu").fill("Saint-Étienne")
    page.get_by_test_id("cf-type").select_option("Difficulté")
    page.get_by_test_id("cf-prix").fill("18")
    tick_coach(page, "Severus Snape")
    tick_coach(page, "Minerva McGonagall")
    page.get_by_test_id("cf-save").click()

    # The new competition opens
    expect(page.get_by_test_id("create-dialog")).to_be_hidden()
    expect(page.get_by_test_id("detail-name")).to_have_text(nom)
    expect(page).to_have_url(re.compile(r"/competitions\?id=\d+$"))
    meta = page.get_by_test_id("detail-meta")
    for text in ("EVT-E2E-1", "14/03/2027 → 15/03/2027", "18,00 €", "Saint-Étienne", "Difficulté"):
        expect(meta).to_contain_text(text)
    # Coaches saved by name
    expect(page.get_by_test_id("detail-coaches")).to_have_text("🏃 Coachs : Minerva McGonagall, Severus Snape")

    def stored():
        doc = test_data.competition_by_name(nom)
        assert (doc["date_competition"], doc["date_fin"], doc["prix"], doc["lieu"], doc["type"]) == ("2027-03-14", "2027-03-15", 18, "Saint-Étienne", "Difficulté")
    eventually(stored)
    page.get_by_test_id("back-link").click()
    page.reload()
    expect(competition_card(page, nom)).to_be_visible()


def test_name_is_required(mobile_page):
    page = open_screen(mobile_page)
    page.get_by_test_id("create-comp").click()
    page.get_by_test_id("cf-save").click()
    expect(page.get_by_test_id("cf-error")).to_have_text("Le nom de l'épreuve est obligatoire.")
    expect(page.get_by_test_id("create-dialog")).to_be_visible()


def test_edit_and_delete_competition(page, test_data):
    nom = unique_name("E2E Edit")
    test_data.create_competition(nom, date=_iso(30), prix=10)
    open_screen(page, "admin", "/bureau/competitions")
    accept_dialogs(page)
    open_competition(page, nom)
    page.get_by_test_id("edit-comp").click()
    expect(page.get_by_test_id("cf-nom")).to_have_value(nom)
    renamed = unique_name("E2E Edited")
    page.get_by_test_id("cf-nom").fill(renamed)
    page.get_by_test_id("cf-prix").fill("22,5")
    page.get_by_test_id("cf-lieu").fill("Lyon")
    tick_coach(page, "Filius Flitwick")
    page.get_by_test_id("cf-save").click()

    expect(page.get_by_test_id("edit-dialog")).to_be_hidden()
    card = competition_card(page, renamed)
    meta = page.get_by_test_id("detail-meta")
    expect(meta).to_contain_text("22,50 €")
    expect(meta).to_contain_text("Lyon")
    expect(card).to_contain_text("Coachs : Filius Flitwick")
    expect(competition_card(page, nom)).to_have_count(0)

    page.get_by_test_id("detail-more").click()
    page.get_by_test_id("delete-comp").click()
    expect(toast(page)).to_contain_text("Compétition supprimée")
    expect(competition_card(page, renamed)).to_have_count(0)
    expect(page.get_by_test_id("comp-detail")).to_have_count(0)

    def deleted():
        assert test_data.competition_by_name(renamed) is None
    eventually(deleted)


def test_archive_and_restore(mobile_page, test_data):
    nom = unique_name("E2E Archive")
    test_data.create_competition(nom, date=_iso(30))
    page = open_screen(mobile_page)
    open_competition(page, nom)
    page.get_by_test_id("detail-more").click()
    page.get_by_test_id("archive-comp").click()
    expect(page.get_by_test_id("detail-meta")).to_contain_text("Archivée")
    page.get_by_test_id("back-link").click()
    expect(competition_card(page, nom)).to_have_count(0)  # archives hidden

    page.get_by_test_id("toggle-archives").click()
    archived = archived_card(page, nom)
    expect(archived).to_contain_text("Archivée")
    archived.click()
    page.get_by_test_id("detail-more").click()
    page.get_by_test_id("unarchive-comp").click()
    expect(page.get_by_test_id("detail-meta")).not_to_contain_text("Archivée")

    def restored():
        assert test_data.competition_by_name(nom)["statut"] == "en_preparation"
    eventually(restored)


# « Archiver les passées » archives every past competition: kept off the other workers while the filter test runs
@pytest.mark.xdist_group("past_competitions")
def test_archive_past_competitions(mobile_page, test_data):
    past, upcoming = unique_name("E2E Past"), unique_name("E2E Upcoming")
    test_data.create_competition(past, date=_iso(-3))
    test_data.create_competition(upcoming, date=_iso(3))
    page = open_screen(mobile_page)
    accept_dialogs(page)
    expect(competition_card(page, past)).to_be_visible()
    page.get_by_test_id("archive-past").click()
    expect(toast(page)).to_contain_text("archivée")
    expect(competition_card(page, past)).to_have_count(0)
    expect(competition_card(page, upcoming)).to_be_visible()

    def archived():
        assert test_data.competition_by_name(past)["statut"] == "close"
    eventually(archived)


@pytest.mark.xdist_group("past_competitions")
def test_search_and_date_filters(page, test_data):
    tag = unique_name("E2E Filter")
    test_data.create_competition(f"{tag} past", date=_iso(-10))
    test_data.create_competition(f"{tag} next", date=_iso(10))
    open_screen(page, "admin", "/bureau/competitions")
    page.get_by_test_id("comp-search").fill(tag.lower())
    cards = page.get_by_test_id("comp-card")
    expect(cards).to_have_count(2)
    page.get_by_test_id("when-past").click()
    expect(cards).to_have_count(1)
    expect(cards).to_contain_text("past")
    page.get_by_test_id("when-upcoming").click()
    expect(cards).to_have_text(re.compile("next"))
    page.get_by_test_id("when-all").click()
    page.get_by_test_id("comp-search").fill("hogwarts lead")
    expect(competition_card(page, SEEDED_COMPETITION)).to_be_visible()


def _read_csv(download, folder) -> list:
    # save_as(): path() is not available with a remote browser (E2E_PLAYWRIGHT_WS)
    target = folder / download.suggested_filename
    download.save_as(target)
    return list(csv.reader(io.StringIO(target.read_text(encoding="utf-8-sig")), delimiter=";"))


def test_competition_csv_export(page, test_data, tmp_path):
    members = test_data.members(competition_only=True)[:3]
    nom = unique_name("E2E Csv")
    test_data.create_competition(nom, date=_iso(26), participants=[m["id"] for m in members], selected=[members[0]["id"]])
    open_screen(page, "admin", "/bureau/competitions")
    open_competition(page, nom)
    with page.expect_download() as info:
        page.get_by_test_id("detail-more").click()
        page.get_by_test_id("export-csv").click()
    rows = _read_csv(info.value, tmp_path)
    assert rows[0][:3] == ["Nom", "Prénom", "N° Licence"]
    assert len(rows) == 1 + len(members)
    participe = rows[0].index("Participe")
    assert sorted(r[participe] for r in rows[1:]) == ["Non", "Non", "Oui"]


def test_coach_changes_competitions_on_desktop(page):
    """Competition changes are open to coaches (server rule); read-only accounts: test_competitions_view.py."""
    open_screen(page, "coach", "/bureau/competitions")
    expect(page.get_by_test_id("create-comp")).to_be_visible()
    open_competition(page, SEEDED_COMPETITION)
    expect(page.get_by_test_id("edit-comp")).to_be_visible()
    expect(page.get_by_test_id("participe-switch").first).to_be_enabled()
