"""Bodies of the club key routes (API contract, plans/club-keys.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.request_body import RequestBody

KeyStatus = Literal["available", "assigned", "archived"]


class Key(BaseModel):
    """A club key and its status."""
    id: int
    code: str
    status: KeyStatus


class KeyIn(RequestBody):
    """A new key: its code (engraved number or club number), unique whatever its case."""
    code: str = Field(min_length=1, max_length=40)
