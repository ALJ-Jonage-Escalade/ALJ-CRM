"""Bodies of the club key routes (API contract, plans/club-keys.md)."""

from __future__ import annotations

import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from api.request_body import RequestBody

KeyStatus = Literal["available", "assigned", "archived"]


class KeyHolder(BaseModel):
    """Who holds a key, since when; member_this_season false: no membership of the active season (to chase up)."""
    user_id: int
    last_name: str
    first_name: str
    given_on: str
    comment: str
    member_this_season: bool
    season: str  # season of the member's record (the active one, else their last one), for the link to it


class Key(BaseModel):
    """A club key, its status and its current holder."""
    id: int
    code: str
    status: KeyStatus
    holder: Optional[KeyHolder] = None


class KeyDone(BaseModel):
    """A key write with nothing else to return."""
    status: Literal["success"]


class KeyIn(RequestBody):
    """A new key: its code (engraved number or club number), unique whatever its case."""
    code: str = Field(min_length=1, max_length=40)


class KeyAssignmentIn(RequestBody):
    """A key handed over to a member of the active season."""
    user_id: int
    given_on: datetime.date
    comment: str = Field(default="", max_length=500)


class KeyReturnIn(RequestBody):
    """A key given back (not before it was handed over)."""
    returned_on: datetime.date
    comment: str = Field(default="", max_length=500)
