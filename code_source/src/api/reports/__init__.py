"""Reports of the Outils page in the Vue app (members map, pivot table), read from the SQLite cache."""

from __future__ import annotations

from domain.constants import get_active_season


def resolve_season(season: str) -> str:
    """The season to read: "", "active" and "default" mean the active season."""
    season = (season or "").strip()
    return get_active_season() if season.lower() in ("", "active", "default") else season
