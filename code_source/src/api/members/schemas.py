"""Bodies of the membership season routes called by the Vue app (API contract, see api/communications/schemas.py)."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel


class SeasonTarifs(BaseModel):
    """The season's HelloAsso tariffs, to link them to a planning slot."""
    status: Literal["success"]
    season: str
    tarifs: List[str]


class Seasons(BaseModel):
    """Season names, most recent first, and the active season."""
    seasons: List[str]
    active: str
