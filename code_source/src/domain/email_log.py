"""The e-mail log: one entry per send action of the app, and what the competition page reads from it.

An entry says who sent what kind of e-mail, about which competitions and members, and for each recipient the address
it went to and whether it left. Bodies are never stored (they hold personal data, and the template and references
rebuild them).

Only e-mails to the competitors (`competition_email`) date their last contact; the other kinds (an internal summary,
the results e-mail) are listed in the history but never make the families look contacted.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Literal, Optional, Sequence, TypedDict, TypeGuard, get_args

EmailKind = Literal["competition_email", "member_email", "competition_all_paid", "results_batch", "attestation",
                    "access_invitation"]
SendStatus = Literal["sent", "failed"]

COMPETITOR_KIND: EmailKind = "competition_email"
SYSTEM_AUTHOR = "system"  # automatic sends: HelloAsso webhook, daily cron


def is_email_kind(value: object) -> TypeGuard[EmailKind]:
    return value in get_args(EmailKind)


def is_send_status(value: object) -> TypeGuard[SendStatus]:
    return value in get_args(SendStatus)


class LoggedRecipient(TypedDict):
    member_id: Optional[int]  # None: an address outside the members (the club's inbox, an invited person)
    email: str  # as sent, even if the member's address was corrected since
    name: str
    status: SendStatus
    error: Optional[str]


class EmailLogEntry(TypedDict):
    at: str  # ISO 8601 UTC
    author: str  # e-mail of the signed-in user, or SYSTEM_AUTHOR
    kind: EmailKind
    template: str  # template name, "" for a free text or a fixed e-mail
    subject: str
    competition_ids: List[int]
    member_ids: List[int]
    recipients: List[LoggedRecipient]


class Competitor(TypedDict):
    member_id: Optional[int]
    email: str


class CompetitorContact(TypedDict):
    member_id: Optional[int]
    email: str
    last_sent_at: Optional[str]  # last e-mail that left for this competitor
    last_failed: bool  # their latest attempt failed (shown as « échec », whatever was sent before)


class ContactSummary(TypedDict):
    competitors: List[CompetitorContact]


def recipient_is(recipient: LoggedRecipient, competitor: Competitor) -> bool:
    """A recipient is this competitor: same member, or same address (any case) when the competitor has no member id."""
    if competitor["member_id"] is not None:
        return recipient["member_id"] == competitor["member_id"]
    return bool(competitor["email"]) and recipient["email"].strip().lower() == competitor["email"].strip().lower()


def contact_summary(entries: Iterable[EmailLogEntry], competitors: Sequence[Competitor]) -> ContactSummary:
    """Each competitor's last contact, from the entries of their competition."""
    to_competitors = sorted((entry for entry in entries if entry["kind"] == COMPETITOR_KIND), key=lambda entry: entry["at"])
    contacts: List[CompetitorContact] = []
    for competitor in competitors:
        last_sent_at: Optional[str] = None
        last_failed = False
        for entry in to_competitors:
            for recipient in entry["recipients"]:
                if recipient_is(recipient, competitor):
                    last_failed = recipient["status"] == "failed"
                    if not last_failed:
                        last_sent_at = entry["at"]
        contacts.append(CompetitorContact(member_id=competitor["member_id"], email=competitor["email"],
                                          last_sent_at=last_sent_at, last_failed=last_failed))
    return ContactSummary(competitors=contacts)


def member_ids_of(recipients: Iterable[LoggedRecipient]) -> List[int]:
    """The members an entry concerns, each once, in order."""
    seen: Dict[int, None] = {}
    for recipient in recipients:
        if recipient["member_id"] is not None:
            seen.setdefault(recipient["member_id"], None)
    return list(seen)
