"""FfmeImportRepository.apply_ffme_matches: an empty value of the file keeps the stored one, and only the member's
purchases of the season become « Terminé », except cancelled or refunded ones."""

from __future__ import annotations

from typing import Any

from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.ffme_import import FfmeImportRepository
from support.member_db import MemberDbTestCase

SEASON = "2026-2027"


class TestApplyFfmeMatches(MemberDbTestCase):

    def _query(self, sql: str, *params: Any) -> list[Any]:
        conn = SqliteDatabase.get_connection()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _execute(self, sql: str) -> None:
        conn = SqliteDatabase.get_connection()
        try:
            conn.execute(sql)
            conn.commit()
        finally:
            conn.close()

    def _user_id(self) -> int:
        return int(self._query("SELECT id FROM users WHERE last_name = 'MARTIN'")[0]["id"])

    def _statuses(self) -> dict[str, str]:
        rows = self._query("SELECT o.order_ref, p.status FROM purchases p JOIN orders o ON o.id = p.order_id")
        return {row["order_ref"]: row["status"] for row in rows}

    def test_apply_ffme_matches_empty_values_keep_stored_ones(self):
        self.seed("1", "Léo", "MARTIN", "Cours ados")
        user_id = self._user_id()
        FfmeImportRepository.apply_ffme_matches([("Terminé", "112233", "P1", "D1", "Certificat", user_id)], SEASON)

        FfmeImportRepository.apply_ffme_matches([("Terminé", "", "", "", "", user_id)], SEASON)

        user = self._query("SELECT licence_ffme, raw_passports, raw_diplomas FROM users WHERE id = ?", user_id)[0]
        self.assertEqual(tuple(user), ("112233", "P1", "D1"))
        self.assertEqual(self._query("SELECT document_sante FROM purchases")[0]["document_sante"], "Certificat")

    def test_apply_ffme_matches_marks_every_purchase_but_cancelled_ones(self):
        for ref, tarif in (("1", "Cours ados"), ("2", "Cours compétition"), ("3", "Cours adultes")):
            self.seed(ref, "Léo", "MARTIN", tarif)
        # Refunded next to paid ones: the member writers would have dropped it, only older data has it
        self._execute("UPDATE purchases SET status = 'Refunded'"
                      " WHERE order_id = (SELECT id FROM orders WHERE order_ref = '3')")

        FfmeImportRepository.apply_ffme_matches([("Terminé", "112233", "", "", "", self._user_id())], SEASON)

        self.assertEqual(self._statuses(), {"1": "Terminé", "2": "Terminé", "3": "Refunded"})

    def test_apply_ffme_matches_leaves_cancelled_only_member_unchanged(self):
        self.seed("1", "Léo", "MARTIN", "Cours ados", status="Canceled")

        FfmeImportRepository.apply_ffme_matches([("Terminé", "112233", "", "", "Certificat", self._user_id())], SEASON)

        self.assertEqual(self._statuses(), {"1": "Canceled"})
        self.assertEqual(self._query("SELECT licence_ffme FROM users")[0]["licence_ffme"], "112233")
