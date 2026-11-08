"""Seasons and the HelloAsso tarifs sold in them."""

from __future__ import annotations

import logging

from domain.constants import DEFAULT_EXTRA_TARIFS
from infrastructure.sqlite.connection import SqliteDatabase

logger = logging.getLogger("alj")


class SeasonRepository:
    @classmethod
    def list_seasons(cls) -> list:
        """Seasons as [{name, is_active}], most recent first."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            rows = conn.execute("SELECT name, is_active FROM seasons WHERE name IS NOT NULL AND name != ''"
                                " ORDER BY name DESC").fetchall()
            return [{"name": r["name"], "is_active": bool(r["is_active"])} for r in rows]
        finally:
            conn.close()

    @classmethod
    def get_season_tarifs(cls, season_name: str) -> list:
        """Retourne la liste triée des tarifs HelloAsso distincts d'une saison (groupes disponibles)."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT p.tarif_name
                FROM purchases p
                JOIN orders o ON o.id = p.order_id
                JOIN seasons s ON s.id = o.season_id
                WHERE s.name = ? AND p.tarif_name IS NOT NULL AND TRIM(p.tarif_name) != ''
                ORDER BY p.tarif_name ASC
            """, (season_name,))
            db_tarifs = [r["tarif_name"].strip() for r in cursor.fetchall()]
            combined = set(db_tarifs) | set(DEFAULT_EXTRA_TARIFS)
            return sorted(combined)
        except Exception as e:
            logger.warning(f"[SQLITE] Erreur lors du chargement des tarifs de la saison {season_name} : {e}")
            return list(DEFAULT_EXTRA_TARIFS)
        finally:
            conn.close()

    @classmethod
    def get_all_tarifs(cls) -> list:
        """Sorted distinct HelloAsso tarif names across every season."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            rows = conn.execute("""
                SELECT DISTINCT tarif_name FROM purchases
                WHERE tarif_name IS NOT NULL AND tarif_name != ''
                ORDER BY tarif_name ASC
            """).fetchall()
            return [r["tarif_name"].strip() for r in rows]
        finally:
            conn.close()
