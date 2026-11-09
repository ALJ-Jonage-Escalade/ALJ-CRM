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
        """
        Phase B de l'import FFME — écrit en base les associations validées :
        updates = [(match_type, licence, passeports, diplomas, document_sante, user_id), ...]
        Met à jour la licence/passeports/diplômes de l'utilisateur, écrit le Document de
        santé (associé à la personne pour la saison active, via purchases) et bascule
        ses achats de la saison active en statut "Terminé" (licence FFME confirmée).
        A database failure is rolled back and raised.
        """
        if not updates:
            return
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            target_season = str(season_name or get_active_season()).strip()

            for u in updates:
                lic = str(u[1] or "").strip()
                passp = str(u[2] or "").strip()
                dipl = str(u[3] or "").strip()
                uid = int(u[5])

                if passp and dipl:
                    cursor.execute("""
                        UPDATE users
                        SET licence_ffme = ?, raw_passports = ?, raw_diplomas = ?
                        WHERE id = ?
                    """, (lic, passp, dipl, uid))
                elif passp:
                    cursor.execute("""
                        UPDATE users
                        SET licence_ffme = ?, raw_passports = ?
                        WHERE id = ?
                    """, (lic, passp, uid))
                elif dipl:
                    cursor.execute("""
                        UPDATE users
                        SET licence_ffme = ?, raw_diplomas = ?
                        WHERE id = ?
                    """, (lic, dipl, uid))
                else:
                    cursor.execute("""
                        UPDATE users
                        SET licence_ffme = ?
                        WHERE id = ?
                    """, (lic, uid))

            cursor.executemany("""
                UPDATE purchases
                SET status = ?, status_normalized = ?, document_sante = ?, updated_at = ?
                WHERE user_id = ? AND order_id IN (
                    SELECT id FROM orders
                    WHERE season_id = (SELECT id FROM seasons WHERE name = ? OR is_active = 1 LIMIT 1)
                )
            """, [(u[0], schema_v2.normalize_status(u[0]), u[4],
                   datetime.datetime.now().isoformat(timespec="seconds"), u[5], target_season) for u in updates])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

