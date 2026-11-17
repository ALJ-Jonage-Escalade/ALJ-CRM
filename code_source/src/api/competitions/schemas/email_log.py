"""Answer of the e-mail log route of a competition (api.competitions.email_log): domain/email_log.py shapes."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class LoggedRecipient(BaseModel):
    member_id: Optional[int] = Field(None, description="None: an address outside the members (the club's inbox)")
    email: str = Field(description="The address the e-mail was sent to, even if corrected since")
    name: str = ""
    status: Literal["sent", "failed"]
    error: Optional[str] = None


class EmailLogEntry(BaseModel):
    """One send action (one click on « Envoyer », one webhook notification, one cron e-mail); no body stored."""
    at: str = Field(description="ISO 8601 UTC")
    author: str = Field(description="E-mail of the person who sent it, « system » for automatic sends")
    kind: Literal["competition_email", "member_email", "competition_all_paid", "results_batch", "attestation",
                  "access_invitation"]
    template: str = ""
    subject: str = ""
    competition_ids: List[int] = []
    member_ids: List[int] = []
    recipients: List[LoggedRecipient] = []


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
