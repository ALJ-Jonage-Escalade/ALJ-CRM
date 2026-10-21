"""Membership seasons (SQLite cache of the crm_* collections).

Knows nothing about HTTP: failures are raised as services.errors.
"""

from __future__ import annotations

from typing import List, TypedDict

from infrastructure.sqlite.seasons import SeasonRepository


class Seasons(TypedDict):
    seasons: List[str]  # names, most recent first
    active: str


class SeasonService:

    @staticmethod
    def list_seasons() -> Seasons:
        """{seasons: names most recent first, active: the active season}. Without a season
        flagged active, the most recent one is."""
        seasons: List[dict] = SeasonRepository.list_seasons()
        names = [s["name"] for s in seasons]
        active = next((s["name"] for s in seasons if s["is_active"]), names[0] if names else "")
        return {"seasons": names, "active": active}
