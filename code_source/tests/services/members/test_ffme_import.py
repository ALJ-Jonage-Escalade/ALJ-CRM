"""Import of the MyFFME licensee list (services/members/ffme.py): matching by licence then by name (a known birth date
of the file that disagrees with the member's rules the match out), then the values written by apply_import."""

from __future__ import annotations

import io
from typing import Any

import openpyxl

from infrastructure.sqlite.connection import SqliteDatabase
from services.members.ffme import apply_import, prepare_licensees
from support.member_db import MemberDbTestCase

BIRTH_FIELD = "champ_Date de naissance de l'adhérent"
HEADER = ["Nom", "Prénom", "N° de licence", "Date de naissance", "Passeports", "Diplômes", "Document de santé"]
SEASON = "2026-2027"


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
        return [row["member"]["id"] for row in prepare_licensees(_workbook_bytes(rows), SEASON)["rows"]]

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

        preparation = prepare_licensees(_workbook_bytes([["MARTIN", "Emma", "111111", "02/04/2015"]]), SEASON)

        self.assertEqual([row["member"]["id"] for row in preparation["rows"]], [emma])
        self.assertEqual((preparation["stats"]["matched_by_licence"], preparation["stats"]["matched_by_name"]), (0, 1))


class TestApplyImport(MemberDbTestCase):
    """What apply_import writes: an empty value of the file keeps the stored one, but an empty health document is
    « ATTENTE »; « Terminé » goes to every purchase of the season but cancelled or refunded ones."""

    def _query(self, sql: str) -> list[Any]:
        conn = SqliteDatabase.get_connection()
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def _execute(self, sql: str) -> None:
        conn = SqliteDatabase.get_connection()
        try:
            conn.execute(sql)
            conn.commit()
        finally:
            conn.close()

    def _import(self, licence: str = "", passports: str = "", diplomas: str = "", health_document: str = "") -> int:
        content = _workbook_bytes([["MARTIN", "Léo", licence, None, passports, diplomas, health_document]])
        return apply_import(SEASON, content)[0]

    def _statuses(self) -> dict[str, str]:
        rows = self._query("SELECT o.order_ref, p.status FROM purchases p JOIN orders o ON o.id = p.order_id")
        return {row["order_ref"]: row["status"] for row in rows}

    def _health_document(self) -> str:
        return self._query("SELECT document_sante FROM purchases")[0]["document_sante"]

    def test_apply_import_empty_values_keep_stored_ones(self):
        self.seed("1", "Léo", "MARTIN", "Cours ados")
        self._import("112233", "P1", "D1", "QS")

        self._import(health_document="QS")

        user = self._query("SELECT licence_ffme, raw_passports, raw_diplomas FROM users")[0]
        self.assertEqual(tuple(user), ("112233", "P1", "D1"))

    def test_apply_import_empty_health_document_is_pending(self):
        self.seed("1", "Léo", "MARTIN", "Cours ados")
        self._import("112233", health_document="QS")

        self._import("112233")

        self.assertEqual(self._health_document(), "ATTENTE")

    def test_apply_import_without_health_document_column_keeps_stored_one(self):
        self.seed("1", "Léo", "MARTIN", "Cours ados")
        self._import("112233", health_document="LOISIR")
        workbook = openpyxl.Workbook()
        workbook.active.append(HEADER[:-1])
        workbook.active.append(["MARTIN", "Léo", "112233"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        apply_import(SEASON, buffer.getvalue())

        self.assertEqual(self._health_document(), "LOISIR")

    def test_apply_import_marks_every_purchase_but_cancelled_ones(self):
        for ref, tarif in (("1", "Cours ados"), ("2", "Cours compétition"), ("3", "Cours adultes")):
            self.seed(ref, "Léo", "MARTIN", tarif)
        # Refunded next to paid ones: the member writers would have dropped it, only older data has it
        self._execute("UPDATE purchases SET status = 'Refunded' WHERE order_id = (SELECT id FROM orders WHERE order_ref = '3')")

        self._import("112233")

        self.assertEqual(self._statuses(), {"1": "Terminé", "2": "Terminé", "3": "Refunded"})

    def test_apply_import_leaves_cancelled_only_member_unchanged(self):
        self.seed("1", "Léo", "MARTIN", "Cours ados", status="Canceled")

        self._import("112233", health_document="QS")

        self.assertEqual(self._statuses(), {"1": "Canceled"})
        self.assertEqual(self._query("SELECT licence_ffme FROM users")[0]["licence_ffme"], "112233")

    def test_apply_import_counts_only_the_members_it_changes(self):
        self.seed("1", "Léo", "MARTIN", "Cours ados")
        self.assertEqual(self._import("112233"), 1)

        self.assertEqual(self._import("112233"), 0)
