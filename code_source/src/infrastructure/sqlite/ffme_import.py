"""Writes of the FFME licensee import (services/members/ffme.py reads the file and matches it)."""

from __future__ import annotations

import datetime
import logging
from typing import Dict, List, TypedDict

from domain.members.ffme_changes import MemberWrite, SeasonPurchase
from domain.members.view import normalize_status
from infrastructure.sqlite.connection import SqliteDatabase

logger = logging.getLogger("alj")


class MemberForMatching(TypedDict):
    id: int
    last_name: str
    first_name: str
    licence_ffme: str
    birth_date: str
    raw_passports: str
    raw_diplomas: str


# Purchases of a season: the one asked for, the active one when it does not exist (parameters: the name, twice)
_SEASON_PURCHASES = """
    SELECT p.id, p.user_id, COALESCE(p.status, '') AS status, COALESCE(p.document_sante, '') AS document_sante
    FROM purchases p JOIN orders o ON o.id = p.order_id
    WHERE o.season_id = (SELECT id FROM seasons WHERE name = ? OR is_active = 1 ORDER BY name = ? DESC LIMIT 1)
"""


class FfmeImportRepository:
    @classmethod
    def list_members_for_matching(cls) -> List[MemberForMatching]:
        """Every member, with what the matching compares (licence, names, birth date) and what the import changes."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            rows = conn.execute("""
                SELECT id, last_name, first_name, COALESCE(licence_ffme, '') AS licence_ffme,
                       COALESCE(birth_date, birth_date_raw, '') AS birth_date,
                       COALESCE(raw_passports, '') AS raw_passports, COALESCE(raw_diplomas, '') AS raw_diplomas
                FROM users
            """).fetchall()
        finally:
            conn.close()
        return [MemberForMatching(id=row["id"], last_name=row["last_name"], first_name=row["first_name"],
                                  licence_ffme=row["licence_ffme"], birth_date=row["birth_date"],
                                  raw_passports=row["raw_passports"], raw_diplomas=row["raw_diplomas"]) for row in rows]

    @classmethod
    def list_season_purchases(cls, season_name: str) -> Dict[int, List[SeasonPurchase]]:
        """The purchases of the season (the active one when it does not exist), by member."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            rows = conn.execute(_SEASON_PURCHASES, (season_name, season_name)).fetchall()
        finally:
            conn.close()
        purchases: Dict[int, List[SeasonPurchase]] = {}
        for row in rows:
            purchases.setdefault(int(row["user_id"]), []).append(
                SeasonPurchase(id=int(row["id"]), status=row["status"], document_sante=row["document_sante"]))
        return purchases

    @classmethod
    def apply_ffme_matches(cls, writes: List[MemberWrite]) -> None:
        """Second step of the FFME import: writes the final values planned by domain.members.ffme_changes (user fields,
        status and health document of the listed purchases). A database failure is rolled back and raised."""
        if not writes:
            return
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            now = datetime.datetime.now().isoformat(timespec="seconds")
            conn.executemany("UPDATE users SET licence_ffme = ?, raw_passports = ?, raw_diplomas = ? WHERE id = ?",
                             [(write["licence"], write["passports"], write["diplomas"], write["user_id"]) for write in writes])
            conn.executemany("UPDATE purchases SET status = ?, status_normalized = ?, document_sante = ?, updated_at = ? WHERE id = ?",
                             [(purchase["status"], normalize_status(purchase["status"]), purchase["document_sante"], now, purchase["id"])
                              for write in writes for purchase in write["purchases"]])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
