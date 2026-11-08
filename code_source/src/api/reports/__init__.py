"""Reports of the Outils page in the Vue app (members map, pivot table), read from the SQLite cache."""

from __future__ import annotations

from typing import Optional

from domain.constants import resolve_season


ALL_SEASONS = "Toutes les saisons"  # the pages' choice for every season


def season_read(season: str) -> Optional[str]:
    """MemberRepository.load_direct_data's argument for a resolved season: None for ALL_SEASONS."""
    return None if season == ALL_SEASONS else season


def resolve_report_season(season: str) -> str:
    """The season to read: ALL_SEASONS (every season) or a season name, the active one when empty
    (domain.constants.resolve_season, InvalidRequest on a bad format)."""
    season = (season or "").strip()
    return ALL_SEASONS if season == ALL_SEASONS else resolve_season(season)
