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
        try:
            with SqliteDatabase.connect() as conn:
                rows = conn.execute("SELECT address, lat, lon FROM geocache").fetchall()
        except Exception as e:
            logger.warning(f"[SQLITE] Erreur lors du chargement du geocache : {e}")
            return {}
        return {row["address"]: [row["lat"], row["lon"]] for row in rows}

    @classmethod
    def save_geocode(cls, address: str, lat: Optional[float], lon: Optional[float]):
        """Sauvegarde ou met à jour les coordonnées d'une adresse dans la table de cache."""
        try:
            with SqliteDatabase.transaction() as conn:
                conn.execute("""
                    INSERT INTO geocache (address, lat, lon)
                    VALUES (?, ?, ?)
                    ON CONFLICT(address) DO UPDATE SET
                        lat = excluded.lat,
                        lon = excluded.lon
                """, (address, lat, lon))
        except Exception as e:
            logger.warning(f"[SQLITE] Erreur lors de la sauvegarde du géocodage de '{address}' : {e}")
