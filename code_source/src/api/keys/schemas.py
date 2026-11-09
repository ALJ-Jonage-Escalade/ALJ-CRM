"""Bodies of the club key routes (API contract, plans/club-keys.md)."""

from __future__ import annotations

import datetime
from typing import List, Literal, Optional, Union

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


class KeyRename(RequestBody):
    """A key's new code (a placeholder replaced, a typo fixed)."""
    code: str = Field(min_length=1, max_length=40)


class KeyAssignmentPatch(RequestBody):
    """Corrected dates and comments of an assignment; returned_on only on a key given back."""
    given_on: datetime.date
    returned_on: Optional[datetime.date] = None
    comment: str = Field(default="", max_length=500)
    return_comment: str = Field(default="", max_length=500)


class KeyAssignmentEntry(BaseModel):
    """Who held the key, from given_on to returned_on (None: still held), who handed it over (by)."""
    kind: Literal["assignment"]
    id: int
    user_id: int
    last_name: str
    first_name: str
    given_on: str
    returned_on: Optional[str]
    comment: str
    return_comment: str
    by: str


class KeyEventEntry(BaseModel):
    """Something else that happened to the key, and the admin who did it."""
    kind: Literal["event"]
    id: int
    type: Literal["archived", "restored", "renamed", "assignment_deleted"]
    date: str
    comment: str
    by: str


KeyHistory = List[Union[KeyAssignmentEntry, KeyEventEntry]]
