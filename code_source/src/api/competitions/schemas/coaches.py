"""Bodies of the coach routes (api.competitions.coaches)."""

from __future__ import annotations

from pydantic import Field

from api.request_body import RequestBody


class CoachIn(RequestBody):
    nom: str = Field(min_length=1)
