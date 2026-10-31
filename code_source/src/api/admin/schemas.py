"""Bodies of the Administration › Accès routes."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from infrastructure.security.roles import RoleName

HistoryAction = Literal["invited", "invitation_resent", "added", "role_changed", "name_changed", "removed", "bootstrap"]


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
    invited_at: Optional[str]
    invitation_expires_at: Optional[str] = Field(description="null: no pending invitation (accepted, or added before invitations)")
    invitation_sent_at: Optional[str] = Field(description="null: the invitation e-mail could not be sent")
    accepted_at: Optional[str]


class AccessEntryIn(BaseModel):
    email: str
    role: RoleName
    display_name: str = ""


class AccessEntryPatch(BaseModel):
    """Fields left out (or null) are kept."""
    role: Optional[RoleName] = None
    display_name: Optional[str] = None


class AccessInvitation(BaseModel):
    """An invitation created or sent again; the entry is kept when its e-mail fails."""
    entry: AccessEntry
    email_sent: bool
    email_error: Optional[str] = Field(description="Why the e-mail was not sent; null when it was")


class AccessHistoryEntry(BaseModel):
    at: str
    author: str = Field(description="E-mail of the admin, or « bootstrap »")
    action: HistoryAction
    target_email: str
    old_role: Optional[RoleName]
    new_role: Optional[RoleName]


class AccessDone(BaseModel):
    status: Literal["success"]

