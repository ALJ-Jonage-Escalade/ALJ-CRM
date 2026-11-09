"""Attendance sheet builder: table selection, planning lookup, layout and the generated workbooks."""
from __future__ import annotations

import datetime
import io
from typing import Any

import openpyxl
import pytest

from exports import presence_sheets
from exports.presence_sheets import (
    AUTONOMOUS_SCHEDULE,
    STACKED_FILENAME,
    SheetLayout,
    generate_presence_sheets,
    planning_items_by_keywords,
    session_dates,
    sheet_groups,
    summarize_planning_matches,
)

TODAY = datetime.date(2026, 11, 8)


def _member(first: str, last: str, tarif: str, birth: str = "1990-05-15", **extra: Any) -> dict[str, Any]:
    return {"first_name": first, "last_name": last, "tarif_name": tarif, "birth_date": birth, "status": "Validated", **extra}


PLANNING = [
    {"groupe": "Loisir lundi", "jour": "Lundi", "horaires": "18:00 - 20:00", "encadrants": ["Camille DIDIER"],
     "helloasso_tarifs": ["Tarif lundi"]},
    {"groupe": "Loisir jeudi", "jour": "Jeudi", "horaires": "18:00 - 20:00", "encadrants": [], "helloasso_tarifs": ["Tarif jeudi"]},
    {"groupe": "Autonomes A", "type": "autonome", "jour": "Mardi", "horaires": "19:00 - 22:00", "helloasso_tarifs": ["Adultes autonomes"]},
    {"groupe": "Autonomes B", "type": "autonome", "jour": "Vendredi", "horaires": "19:00 - 22:00", "helloasso_tarifs": ["Jeunes autonomes"]},
]
TARIFS = {"Loisir lundi": ["Tarif lundi"], "Loisir jeudi": ["Tarif jeudi"],
          "Autonomes A": ["Adultes autonomes"], "Autonomes B": ["Jeunes autonomes"]}
MEMBERS = [
    _member("zoe", "durand", "Tarif lundi"),
    _member("Adam", "Petit", "Tarif lundi"),
    _member("Adam", "PETIT", "Tarif lundi"),                       # second registration of the same person
    _member("Remi", "Rembourse", "Tarif lundi", status="Refunded"),
    _member("Jules", "Martin", "Tarif jeudi", birth="2012-01-01", parental_auth_autonomous="Oui"),
    _member("Ines", "Leroy", "Adultes autonomes", document_sante="ATTENTE"),
    _member("Noah", "Roux", "Jeunes autonomes"),
]


@pytest.fixture(autouse=True)
def _no_qrcode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(presence_sheets, "find_group_qrcode", lambda *names: None)
    monkeypatch.setattr(presence_sheets, "get_group_qrcode", lambda link, group: None)


@pytest.mark.parametrize(("layout", "authorization", "health", "first_date"), [
    (SheetLayout(show_badges=False, show_authorization=False, show_health=False), None, None, 3),
    (SheetLayout(show_badges=False, show_authorization=False, show_health=True), None, 3, 4),
    (SheetLayout(show_badges=True, show_authorization=False, show_health=True), None, 6, 7),
    (SheetLayout(show_badges=True, show_authorization=True, show_health=False), 6, None, 7),
    (SheetLayout(show_badges=True, show_authorization=True, show_health=True), 6, 7, 8),
    (SheetLayout(show_badges=False, show_authorization=True, show_health=True), 3, 4, 5),
])
def test_layout_columns(layout: SheetLayout, authorization: int | None, health: int | None, first_date: int) -> None:
    assert (layout.authorization_column, layout.health_column, layout.first_date_column) == (authorization, health, first_date)


def test_cours_groups_list_active_members_once_sorted_by_first_name() -> None:
    groups = sheet_groups(["Loisir lundi", "Loisir jeudi"], MEMBERS, "cours", TARIFS, TODAY)
    assert [g.name for g in groups] == ["Loisir lundi", "Loisir jeudi"]
    assert [m["first_name"] for m in groups[0].members] == ["Adam", "zoe"]


def test_autonome_merges_groups_and_adds_authorised_minors() -> None:
    [group] = sheet_groups(["Autonomes A", "Autonomes B"], MEMBERS, "autonome", TARIFS, TODAY)
    assert group.name == "Autonomes A & Autonomes B"
    assert group.lookup_name == "Autonomes A"
    assert [m["first_name"] for m in group.members] == ["Ines", "Jules", "Noah"]


def test_a_selected_virtual_group_replaces_the_tariffs_it_covers() -> None:
    selected = ["Adultes & Jeunes Adultes autonomes", "Adultes autonomes"]
    assert [g.name for g in sheet_groups(selected, [], "cours", {}, TODAY)] == ["Adultes & Jeunes Adultes autonomes"]


def test_summarize_planning_matches() -> None:
    matches = [
        {"groupe": "Cours", "jour": "Lundi", "horaires": "18:00 - 20:00", "encadrants": ["Camille DIDIER"]},
        {"groupe": "Cours", "jour": "Lundi / Jeudi", "horaires": "20:00 - 21:00", "encadrants": ["camille didier", "Max ROUX"]},
    ]
    slot = summarize_planning_matches(matches, "Cours")
    assert slot.planning_group == "Cours"
    assert slot.coaches == ["Camille DIDIER", "Max ROUX"]
    assert slot.days == ["Lundi", "Jeudi"]
    assert slot.schedule == "Lundi 18:00 - 20:00, Lundi / Jeudi 20:00 - 21:00"
    assert summarize_planning_matches(matches, "Adultes autonomes").schedule == AUTONOMOUS_SCHEDULE


def test_keyword_lookup_compares_the_start_hour() -> None:
    planning = [{"groupe": "Enfants 1", "jour": "Mercredi", "horaires": "18:00 - 19:00"},
                {"groupe": "Enfants 2", "jour": "Mercredi", "horaires": "08:00 - 09:00"}]
    assert [i["groupe"] for i in planning_items_by_keywords("Loisir Enfants mercredi 8h", planning)] == ["Enfants 2"]


def test_session_dates_skip_holidays() -> None:
    days = session_dates(["Mercredi"], datetime.date(2026, 11, 4), datetime.date(2026, 11, 18))
    assert days == [datetime.date(2026, 11, 4), datetime.date(2026, 11, 18)]   # 11/11 is a public holiday
    assert session_dates(["Mercredi"], None, datetime.date(2026, 11, 18)) == []


def _sheet(content: bytes) -> Any:
    return openpyxl.load_workbook(io.BytesIO(content)).active


def test_one_file_per_course_repeats_the_column_headers_when_printed() -> None:
    files = generate_presence_sheets(["Loisir lundi", "Loisir jeudi"], MEMBERS, PLANNING, variant="cours", group_tarifs=TARIFS,
                                     first_day=datetime.date(2026, 11, 9), last_day=datetime.date(2026, 11, 23), today=TODAY)
    assert [f.filename for f in files] == ["Feuille_Presence_Loisir_lundi.xlsx", "Feuille_Presence_Loisir_jeudi.xlsx"]
    ws = _sheet(files[0].content)
    assert ws["A1"].value == "Loisir lundi"
    assert ws["A2"].value == "🕐 Horaire : Lundi 18:00 - 20:00"
    assert ws["A3"].value == "🧑‍🏫 Encadrants : Camille DIDIER"
    assert ws["A4"].value == "👥 Total élèves : 2"
    assert [ws.cell(row=6, column=c).value for c in range(1, 6)] == ["Prénom", "Nom", "09/11", "16/11", "23/11"]
    assert [ws.cell(row=7, column=c).value for c in (1, 2)] == ["Adam", "PETIT"]
    assert ws.print_title_rows == "$6:$6"
    assert ws.page_setup.paperSize == 8


def test_autonome_sheet_has_badges_authorisation_and_health_columns() -> None:
    [file] = generate_presence_sheets(["Autonomes A", "Autonomes B"], MEMBERS, PLANNING, variant="autonome", group_tarifs=TARIFS,
                                      show_health_col=True, today=TODAY)
    ws = _sheet(file.content)
    assert [ws.cell(row=6, column=c).value for c in range(1, 9)] == [
        "Prénom", "Nom", "Badge rouge", "Bloc", "Passeport Orange", "Autorisation", "Santé", "Date"]
    rows = {ws.cell(row=r, column=1).value: (ws.cell(row=r, column=6).value, ws.cell(row=r, column=7).value) for r in (7, 8, 9)}
    assert rows == {"Ines": (None, "✗"), "Jules": ("🧗", None), "Noah": (None, None)}


def test_same_sheet_stacks_every_course_in_one_workbook() -> None:
    [file] = generate_presence_sheets(["Loisir lundi", "Loisir jeudi"], MEMBERS, PLANNING, variant="cours", group_tarifs=TARIFS,
                                      same_sheet=True, today=TODAY)
    assert file.filename == STACKED_FILENAME
    ws = _sheet(file.content)
    titles = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
    assert "Loisir lundi" in titles and "Loisir jeudi" in titles
    assert len(ws.row_breaks.brk) == 1


def test_missing_template_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(presence_sheets, "find_doc_template", lambda name: str(tmp_path / name))
    with pytest.raises(FileNotFoundError):
        generate_presence_sheets(["Loisir lundi"], MEMBERS, PLANNING, variant="cours")
