"""Geocoding cache (`geocache` table): address -> (lat, lon)."""

from __future__ import annotations

import logging
from typing import Optional

from infrastructure.sqlite.connection import SqliteDatabase

logger = logging.getLogger("alj")


class GeocacheRepository:
    @classmethod
    def get_geocache(cls) -> dict:
        """Récupère tout le cache géocodage sous forme de dictionnaire {adresse: [lat, lon]}."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT address, lat, lon FROM geocache")
            rows = cursor.fetchall()
            return {row["address"]: [row["lat"], row["lon"]] for row in rows}
        except Exception as e:
            logger.warning(f"[SQLITE] Erreur lors du chargement du geocache : {e}")
            return {}
        finally:
            conn.close()

    @classmethod
    def save_geocode(cls, address: str, lat: Optional[float], lon: Optional[float]):
        """Sauvegarde ou met à jour les coordonnées d'une adresse dans la table de cache."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO geocache (address, lat, lon)
                VALUES (?, ?, ?)
                ON CONFLICT(address) DO UPDATE SET
                    lat = excluded.lat,
                    lon = excluded.lon
            """, (address, lat, lon))
            conn.commit()
        except Exception as e:
            logger.warning(f"[SQLITE] Erreur lors de la sauvegarde du géocodage de '{address}' : {e}")
            conn.rollback()
        finally:
            conn.close()
