"""Matching of the MyFFME licensee list (services/members/ffme.prepare_licensees): by licence then by name, a known
birth date of the file that disagrees with the member's ruling the match out."""

from __future__ import annotations

import io

import openpyxl

from infrastructure.sqlite.connection import SqliteDatabase
from services.members.ffme import prepare_licensees
from support.member_db import MemberDbTestCase

BIRTH_FIELD = "champ_Date de naissance de l'adhérent"
HEADER = ["Nom", "Prénom", "N° de licence", "Date de naissance"]


def _workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    for row in [HEADER, *rows]:
        workbook.active.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestPrepareLicensees(MemberDbTestCase):

    def _seed(self, ref: str, first_name: str, birth_date: str, licence: str = "") -> int:
        self.seed(ref, first_name, "MARTIN", "Cours ados", **{BIRTH_FIELD: birth_date})
        conn = SqliteDatabase.get_connection()
        try:
            user_id = int(conn.execute("SELECT MAX(id) AS id FROM users").fetchone()["id"])
            conn.execute("UPDATE users SET licence_ffme = ? WHERE id = ?", (licence, user_id))
            conn.commit()
        finally:
            conn.close()
        return user_id

    def _matched_ids(self, rows: list[list[object]]) -> list[int]:
        return [update[5] for update in prepare_licensees(_workbook_bytes(rows))["updates"]]

    def test_prepare_licensees_homonyms_told_apart_by_birth_date(self):
        self._seed("1", "Léo", "2015-04-02")
        younger = self._seed("2", "Léo", "2017-03-10")

        self.assertEqual(self._matched_ids([["MARTIN", "Léo", "", "10/03/2017"]]), [younger])

    def test_prepare_licensees_homonyms_without_birth_date_left_unmatched(self):
        self._seed("1", "Léo", "2015-04-02")
        self._seed("2", "Léo", "2017-03-10")

        self.assertEqual(self._matched_ids([["MARTIN", "Léo", "", None]]), [])

    def test_prepare_licensees_name_with_other_birth_date_left_unmatched(self):
        self._seed("1", "Léo", "2015-04-02")

        self.assertEqual(self._matched_ids([["MARTIN", "Léo", "", "10/03/2017"]]), [])

    def test_prepare_licensees_unknown_birth_date_still_matches_by_name(self):
        leo = self._seed("1", "Léo", "2015-04-02")

        self.assertEqual(self._matched_ids([["MARTIN", "Léo", "", None]]), [leo])

    def test_prepare_licensees_sibling_licence_falls_back_to_name(self):
        self._seed("1", "Léo", "2017-03-10", licence="111111")
        emma = self._seed("2", "Emma", "2015-04-02")

        preparation = prepare_licensees(_workbook_bytes([["MARTIN", "Emma", "111111", "02/04/2015"]]))

        self.assertEqual([update[5] for update in preparation["updates"]], [emma])
        self.assertEqual((preparation["stats"]["matched_by_licence"], preparation["stats"]["matched_by_name"]), (0, 1))
