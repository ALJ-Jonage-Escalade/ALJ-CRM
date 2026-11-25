"""Answer of the e-mail log route of a competition (api.competitions.email_log): domain/communications/email_log.py shapes.
The log entries themselves are the app-wide model of api.communications.schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from api.communications.schemas import EmailLogEntry


class CompetitorLastContact(BaseModel):
    member_id: Optional[int] = None
    email: str = ""
    last_sent_at: Optional[str] = Field(None, description="Last competitor e-mail that left for this competitor")
    last_failed: bool = Field(False, description="Their latest attempt failed")


class ContactSummary(BaseModel):
    competitors: List[CompetitorLastContact] = []


class CompetitionEmailLog(BaseModel):
    """Every send about the competition, newest first, and its competitors' last contacts."""
    entries: List[EmailLogEntry]
    summary: ContactSummary
