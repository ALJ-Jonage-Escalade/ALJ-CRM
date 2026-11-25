"""FFME export: the club's contact address stands in for a new member with no e-mail."""

from __future__ import annotations

import csv
from pathlib import Path

from exports.membership_excel import generate_ffme_csv

_MEMBER = {
    "first_name": "Neville",
    "last_name": "Londubat",
    "birth_date": "30/07/1980",
    "sex": "M",
    "amount": 150,
    "tarif_name": "Adulte",
    "order_ref": "CMD-1",
}


def _exported_cells(tmp_path: Path, **fields: str) -> list[str]:
    output = tmp_path / "ffme.csv"
    generate_ffme_csv([{**_MEMBER, **fields}], output_path=str(output))
    with open(output, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert len(rows) == 2, rows  # header + the member
    return rows[1]


def test_new_member_without_email_gets_the_club_contact_address(tmp_path: Path) -> None:
    assert "contact@alj-escalade.fr" in _exported_cells(tmp_path)


def test_member_with_email_keeps_it(tmp_path: Path) -> None:
    cells = _exported_cells(tmp_path, email_primary="neville@alj.example")
    assert "neville@alj.example" in cells
    assert "contact@alj-escalade.fr" not in cells
