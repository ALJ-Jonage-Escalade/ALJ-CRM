"""History of the HelloAsso membership imports, in Firestore: one write-once document per import (who, when, season,
campaign, counts per bucket, each registration with the admin's decision and what was written), and one per membership
detached from HelloAsso on the member record (`kind: "detach"`).

Read and written by the server only (firestore.rules refuses every client). No `crm_` prefix: not copied into the
SQLite cache. Dates are ISO 8601 strings in UTC: they sort as text.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, NotRequired, Optional, TypedDict

from infrastructure.firestore.client import FirestoreClient

COLLECTION = "helloasso_membership_imports"


class CorrectedField(TypedDict):
    field: str
    helloasso_value: str
    value: str  # as the admin typed it


class ImportedItem(TypedDict):
    item_id: int
    bucket: str  # bucket of the plan applied
    decision: str  # the admin's choice ("import", "skip", "create", "link:<id>", "attach:<id>"); "skip" when none was sent
    action: str  # what was written: create | attach | update | backfill | assign, "" for nothing
    comment: NotRequired[str]  # the admin's comment (attach by hand)
    corrections: NotRequired[List[CorrectedField]]  # the admin's corrections applied (author: the import's)


class ImportHistoryEntry(TypedDict):
    at: str
    author: str  # e-mail of the admin
    season: str
    campaign: str
    counts: Dict[str, int]  # registrations per bucket
    items: List[ImportedItem]


class DetachHistoryEntry(TypedDict):
    """A membership detached from its HelloAsso registration from the member record (deleted), between two imports."""
    kind: str  # "detach" (an import has no kind)
    at: str
    author: str  # e-mail of the admin
    season: str
    item_id: int
    order_ref: str
    user_id: int
    member: str  # "LAST First", readable once the membership is deleted
    purchase_id: int
    tarif: str
    amount: Optional[float]
    reason: str


class MembershipImportHistory:

    @staticmethod
    def record(entry: ImportHistoryEntry | DetachHistoryEntry) -> str:
        """Writes the entry (an import or a detach); returns its id (the date first, readable in the console, then a
        random part)."""
        entry_id = f"{entry['at']}-{uuid.uuid4().hex[:8]}"
        FirestoreClient.upsert_document(COLLECTION, entry_id, dict(entry))
        return entry_id

    @staticmethod
    def latest() -> Optional[ImportHistoryEntry]:
        """The latest import, None before the first one."""
        docs = FirestoreClient.list_latest(COLLECTION, "at", 1)
        if not docs:
            return None
        doc = docs[0]
        return ImportHistoryEntry(at=str(doc.get("at") or ""), author=str(doc.get("author") or ""), season=str(doc.get("season") or ""),
                                  campaign=str(doc.get("campaign") or ""), counts=dict(doc.get("counts") or {}),
                                  items=list(doc.get("items") or []))
