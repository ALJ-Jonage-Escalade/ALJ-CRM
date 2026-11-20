"""The e-mail log: every sender records its send here, and the competition page reads a competition's history.

`record_send` never raises: the e-mails are gone when it runs, so a store failure is a warning and a notice for the
person who sent them (the dates shown are then incomplete), never an error that would make them send again.
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import Iterable, List, Optional, Sequence, TypedDict

from domain.email_log import (
    Competitor,
    ContactSummary,
    EmailKind,
    EmailLogEntry,
    LoggedRecipient,
    contact_summary,
    member_ids_of,
)
from infrastructure.firestore.email_log import EmailLogStore, FirestoreEmailLogStore
from services.competitions.store import require_competition, storage

logger = logging.getLogger("alj")

# What the pages and the log say of a recipient the mailer refused (the server's reason stays in the logs)
SEND_FAILED = "Erreur lors de l'envoi (détails dans les journaux)."
NOT_RECORDED = "E-mail envoyé, mais non enregistré dans l'historique des envois."

_store: Optional[EmailLogStore] = None
_store_lock = threading.Lock()


def current_store() -> EmailLogStore:
    """The log store of the server (Firestore), created on first use."""
    global _store
    with _store_lock:
        if _store is None:
            _store = FirestoreEmailLogStore()
        return _store


def install(store: Optional[EmailLogStore]) -> None:
    """Replaces the store (tests); None goes back to Firestore on next use."""
    global _store
    with _store_lock:
        _store = store


def logged_recipient(email: str, name: str = "", member_id: Optional[int] = None,
                     error: Optional[str] = None) -> LoggedRecipient:
    """One recipient of a send: sent, or failed with its error."""
    return LoggedRecipient(member_id=member_id, email=email.strip(), name=name.strip(),
                           status="failed" if error else "sent", error=error or None)


def record_send(kind: EmailKind, author: str, recipients: Sequence[LoggedRecipient], subject: str,
                template: str = "", competition_ids: Iterable[int] = ()) -> Optional[str]:
    """Writes one entry for a send action; returns NOT_RECORDED when the store failed (logged), else None."""
    entry = EmailLogEntry(
        at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        author=author,
        kind=kind,
        template=template,
        subject=subject,
        competition_ids=list(dict.fromkeys(competition_ids)),
        member_ids=member_ids_of(recipients),
        recipients=list(recipients),
    )
    try:
        current_store().add_entry(entry)
    except Exception:  # the e-mails left: whatever broke the log, the send itself succeeded
        logger.warning("E-mail log: %s send by %s not recorded", kind, author, exc_info=True)
        return NOT_RECORDED
    return None


class CompetitionHistory(TypedDict):
    entries: List[EmailLogEntry]  # newest first
    summary: ContactSummary


@storage
def competition_history(competition_id: int) -> CompetitionHistory:
    """Every send about the competition (NotFound for an unknown one), with its competitors' last contacts."""
    competition = require_competition(competition_id)
    competitors = [Competitor(member_id=p.get("adherent_id"), email=str(p.get("email") or ""))
                   for p in competition.get("participants") or []]
    entries = sorted(current_store().list_for_competition(competition_id), key=lambda entry: entry["at"], reverse=True)
    return CompetitionHistory(entries=entries, summary=contact_summary(entries, competitors))
