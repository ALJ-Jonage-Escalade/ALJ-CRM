"""Reports of the Outils page in the Vue app (members map, pivot table), read from the SQLite cache."""

from __future__ import annotations

from typing import Optional

from domain.constants import get_active_season


ALL_SEASONS = "Toutes les saisons"  # the pages' choice for every season


def season_read(season: str) -> Optional[str]:
    """MemberRepository.load_direct_data's argument for a resolved season: None for ALL_SEASONS."""
    return None if season == ALL_SEASONS else season


def resolve_season(season: str) -> str:
    """The season to read: "", "active" and "default" mean the active season."""
    season = (season or "").strip()
    return get_active_season() if season.lower() in ("", "active", "default") else season
