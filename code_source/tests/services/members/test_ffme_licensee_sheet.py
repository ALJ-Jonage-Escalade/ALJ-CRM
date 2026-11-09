"""Reading of the MyFFME licensee export (services/members/ffme.py): header row, title row above it, blank rows."""

from __future__ import annotations

import datetime
import io

import openpyxl

from services.members.ffme import LAST_NAME, LICENCE, _read_licensee_sheet


def _workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


HEADER = ["Nom", "Prénom", "N° de licence", "Date de naissance"]


def test_read_licensee_sheet_header_on_first_row() -> None:
    content = _workbook_bytes([HEADER, ["Potter", "Harry", 636947, datetime.datetime(2010, 7, 31)], [None, None, None, None]])
    sheet = _read_licensee_sheet(content)
    assert sheet["columns"] == HEADER
    assert len(sheet["rows"]) == 1  # the blank row is skipped
    assert sheet["rows"][0][LICENCE] == 636947


def test_read_licensee_sheet_title_row_above_header() -> None:
    content = _workbook_bytes([["Export des licenciés"], HEADER, ["Granger", "Hermione", "123456", None]])
    sheet = _read_licensee_sheet(content)
    assert LAST_NAME in sheet["columns"]
    assert sheet["rows"][0][LAST_NAME] == "Granger"


def test_read_licensee_sheet_missing_column_keeps_first_header() -> None:
    content = _workbook_bytes([["Nom", "Prénom"], ["Weasley", "Ron"]])
    sheet = _read_licensee_sheet(content)
    assert sheet["columns"] == ["Nom", "Prénom"]
