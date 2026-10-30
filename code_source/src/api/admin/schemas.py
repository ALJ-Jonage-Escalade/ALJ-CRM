"""Bodies of the Administration › Accès routes."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from infrastructure.security.roles import RoleName

HistoryAction = Literal["added", "role_changed", "name_changed", "removed", "request_granted", "request_dismissed", "bootstrap"]


class AccessEntry(BaseModel):
    """A person with access to the CRM."""
    email: str
    role: RoleName
    display_name: str
    last_sign_in_at: Optional[str] = Field(description="ISO date of the last sign-in, at most once a day; null: never")
    created_at: Optional[str]
    created_by: Optional[str]
    updated_at: Optional[str]
    updated_by: Optional[str]


class AccessEntryIn(BaseModel):
    email: str
    role: RoleName
    display_name: str = ""


class AccessEntryPatch(BaseModel):
    """Fields left out (or null) are kept."""
    role: Optional[RoleName] = None
    display_name: Optional[str] = None


class AccessRequest(BaseModel):
    """A verified Google account that signed in without access."""
    email: str
    google_display_name: str
    first_requested_at: str
    last_requested_at: str


class AccessGrant(BaseModel):
    role: RoleName
    display_name: Optional[str] = Field(default=None, description="null: the Google display name of the request")


class AccessHistoryEntry(BaseModel):
    at: str
    author: str = Field(description="E-mail of the admin, or « bootstrap »")
    action: HistoryAction
    target_email: str
    old_role: Optional[RoleName]
    new_role: Optional[RoleName]


class AccessDone(BaseModel):
    status: Literal["success"]

