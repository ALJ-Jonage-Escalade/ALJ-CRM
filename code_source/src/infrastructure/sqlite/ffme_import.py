"""Writes of the FFME licensee import (services/members/ffme.py reads the file and matches it)."""

from __future__ import annotations

import datetime
import logging
from typing import List, Optional, Tuple, TypedDict

from domain.constants import get_active_season
from infrastructure.sqlite import schema_v2
from infrastructure.sqlite.connection import SqliteDatabase

logger = logging.getLogger("alj")

# A match to write: (purchase status, licence, passports, diplomas, health document, user id)
FfmeMatch = Tuple[str, str, str, str, str, int]


class MemberForMatching(TypedDict):
    id: int
    last_name: str
    first_name: str
    licence_ffme: str
    birth_date: str


class FfmeImportRepository:
    @classmethod
    def list_members_for_matching(cls) -> List[MemberForMatching]:
        """Every member, with what the matching compares (licence, names) and shows (birth date)."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            rows = conn.execute("""
                SELECT id, last_name, first_name, licence_ffme,
                       COALESCE(birth_date, birth_date_raw, '') AS birth_date
                FROM users
            """).fetchall()
        finally:
            conn.close()
        return [MemberForMatching(id=row["id"], last_name=row["last_name"], first_name=row["first_name"],
                                  licence_ffme=row["licence_ffme"], birth_date=row["birth_date"]) for row in rows]

    @classmethod
    def apply_ffme_matches(cls, updates: List[FfmeMatch], season_name: Optional[str] = None) -> None:
        """Second step of the FFME import: writes the validated matches (see FfmeMatch). Updates each member's
        licence, passports and diplomas, and sets the status and health document of their purchases of the season
        (the active one by default). A database failure is rolled back and raised."""
        if not updates:
            return
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            target_season = str(season_name or get_active_season()).strip()
            now = datetime.datetime.now().isoformat(timespec="seconds")

            # An empty passport or diploma cell keeps the stored value
            cursor.executemany("""
                UPDATE users
                SET licence_ffme = ?,
                    raw_passports = COALESCE(NULLIF(?, ''), raw_passports),
                    raw_diplomas = COALESCE(NULLIF(?, ''), raw_diplomas)
                WHERE id = ?
            """, [(str(licence or "").strip(), str(passports or "").strip(), str(diplomas or "").strip(), int(user_id))
                  for _, licence, passports, diplomas, _, user_id in updates])

            cursor.executemany("""
                UPDATE purchases
                SET status = ?, status_normalized = ?, document_sante = ?, updated_at = ?
                WHERE user_id = ? AND order_id IN (
                    SELECT id FROM orders
                    -- the season asked for, the active one when it does not exist
                    WHERE season_id = (SELECT id FROM seasons WHERE name = ? OR is_active = 1 ORDER BY name = ? DESC LIMIT 1)
                )
            """, [(status, schema_v2.normalize_status(status), health_document, now, user_id, target_season, target_season)
                  for status, _, _, _, health_document, user_id in updates])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

