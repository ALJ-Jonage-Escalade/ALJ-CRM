"""The e-mail log in Firestore: collection `email_log`, one write-once document per send action.

Read and written by the server only (firestore.rules refuses every client). No `crm_` prefix: not copied into the
SQLite cache. A competition's entries are found with `array-contains` on `competition_ids`, without `orderBy`: no
composite index to deploy, the caller sorts them.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Protocol

from domain.email_log import EmailLogEntry, LoggedRecipient, is_email_kind, is_send_status
from infrastructure.firestore.client import META_KEYS, FirestoreClient

logger = logging.getLogger("alj")

COLLECTION = "email_log"


class EmailLogStore(Protocol):
    """Storage of the e-mail log (Firestore in production, in memory in the tests)."""

    def add_entry(self, entry: EmailLogEntry) -> None: ...
    def list_for_competition(self, competition_id: int) -> List[EmailLogEntry]:
        """The entries about this competition, in no particular order."""
        ...


def _optional_int(value: object) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _recipient(raw: object) -> Optional[LoggedRecipient]:
    if not isinstance(raw, dict) or not is_send_status(raw.get("status")):
        return None
    return LoggedRecipient(member_id=_optional_int(raw.get("member_id")), email=str(raw.get("email") or ""),
                           name=str(raw.get("name") or ""), status=raw["status"], error=raw.get("error"))


def log_entry(doc: Dict[str, Any]) -> Optional[EmailLogEntry]:  # Any: a Firestore document
    """The entry of a stored document; None for a kind this version does not know."""
    kind = doc.get("kind")
    if not is_email_kind(kind):
        logger.warning("E-mail log: entry %s has an unknown kind, left out", doc.get("_doc_id"))
        return None
    recipients = [recipient for recipient in map(_recipient, doc.get("recipients") or []) if recipient is not None]
    return EmailLogEntry(
        at=str(doc.get("at") or ""),
        author=str(doc.get("author") or ""),
        kind=kind,
        template=str(doc.get("template") or ""),
        subject=str(doc.get("subject") or ""),
        competition_ids=[i for i in map(_optional_int, doc.get("competition_ids") or []) if i is not None],
        member_ids=[i for i in map(_optional_int, doc.get("member_ids") or []) if i is not None],
        recipients=recipients,
    )


class FirestoreEmailLogStore:
    """EmailLogStore on the project's Firestore database (through FirestoreClient)."""

    def add_entry(self, entry: EmailLogEntry) -> None:
        # Id: the date first (readable in the console), then a random part (two sends in the same second)
        fields = {key: value for key, value in dict(entry).items() if key not in META_KEYS}
        FirestoreClient.upsert_document(COLLECTION, f"{entry['at']}-{uuid.uuid4().hex[:8]}", fields)

    def list_for_competition(self, competition_id: int) -> List[EmailLogEntry]:
        entries = (log_entry(doc) for doc in FirestoreClient.list_containing(COLLECTION, "competition_ids", competition_id))
        return [entry for entry in entries if entry is not None]
