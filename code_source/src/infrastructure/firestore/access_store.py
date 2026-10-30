"""Who may use the CRM: the access list, the access requests and their history, in Firestore.

Three collections, read and written by the server only (firestore.rules refuses every client). No `crm_`
prefix: they are not copied into the SQLite cache.
- `access_roles`: one document per normalised e-mail (its id), with the role. The only source of roles.
- `access_requests`: one document per normalised e-mail that signed in without access.
- `access_history`: write-once entries, one per change.

Dates are ISO 8601 strings in UTC (`2026-10-30T09:15:00+00:00`): they sort as text.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Protocol, TypedDict

from infrastructure.firestore.client import META_KEYS, FirestoreClient

ROLES_COLLECTION = "access_roles"
REQUESTS_COLLECTION = "access_requests"
HISTORY_COLLECTION = "access_history"


class RoleEntry(TypedDict):
    email: str
    role: str  # admin | coach | readonly
    display_name: str
    last_sign_in_at: Optional[str]
    created_at: Optional[str]
    created_by: Optional[str]
    updated_at: Optional[str]
    updated_by: Optional[str]


class AccessRequestEntry(TypedDict):
    email: str
    google_display_name: str
    first_requested_at: str
    last_requested_at: str
    dismissed_at: Optional[str]


class HistoryEntry(TypedDict):
    at: str
    author: str  # e-mail of the admin, or "bootstrap"
    action: str  # added | role_changed | name_changed | removed | request_granted | request_dismissed | bootstrap
    target_email: str
    old_role: Optional[str]
    new_role: Optional[str]


class AccessStore(Protocol):
    """Storage of the access list (Firestore in production, in memory in the tests)."""

    def list_roles(self) -> List[RoleEntry]: ...
    def get_role(self, email: str) -> Optional[RoleEntry]: ...
    def create_role(self, entry: RoleEntry) -> bool:
        """Writes the entry unless one exists for this e-mail (False then, nothing written)."""
        ...
    def save_role(self, entry: RoleEntry) -> None: ...
    def update_role(self, email: str, fields: Dict[str, Any]) -> None: ...  # Any: values of RoleEntry fields
    def delete_role(self, email: str) -> None: ...
    def list_requests(self) -> List[AccessRequestEntry]: ...
    def get_request(self, email: str) -> Optional[AccessRequestEntry]: ...
    def save_request(self, entry: AccessRequestEntry) -> None: ...
    def delete_request(self, email: str) -> None: ...
    def add_history(self, entry: HistoryEntry) -> None: ...
    def list_history(self) -> List[HistoryEntry]: ...


def _role_entry(doc: Dict[str, Any]) -> RoleEntry:  # Any: a Firestore document
    return RoleEntry(
        email=str(doc.get("email") or doc.get("_doc_id") or ""),
        role=str(doc.get("role") or ""),
        display_name=str(doc.get("display_name") or ""),
        last_sign_in_at=doc.get("last_sign_in_at"),
        created_at=doc.get("created_at"),
        created_by=doc.get("created_by"),
        updated_at=doc.get("updated_at"),
        updated_by=doc.get("updated_by"),
    )


def _request_entry(doc: Dict[str, Any]) -> AccessRequestEntry:  # Any: a Firestore document
    return AccessRequestEntry(
        email=str(doc.get("email") or doc.get("_doc_id") or ""),
        google_display_name=str(doc.get("google_display_name") or ""),
        first_requested_at=str(doc.get("first_requested_at") or ""),
        last_requested_at=str(doc.get("last_requested_at") or ""),
        dismissed_at=doc.get("dismissed_at"),
    )


def _history_entry(doc: Dict[str, Any]) -> HistoryEntry:  # Any: a Firestore document
    return HistoryEntry(
        at=str(doc.get("at") or ""),
        author=str(doc.get("author") or ""),
        action=str(doc.get("action") or ""),
        target_email=str(doc.get("target_email") or ""),
        old_role=doc.get("old_role"),
        new_role=doc.get("new_role"),
    )


def _fields(entry: Any) -> Dict[str, Any]:  # Any: one of the TypedDicts above
    return {k: v for k, v in dict(entry).items() if k not in META_KEYS}


class FirestoreAccessStore:
    """AccessStore on the project's Firestore database (through FirestoreClient)."""

    def list_roles(self) -> List[RoleEntry]:
        return [_role_entry(doc) for doc in FirestoreClient.list_documents(ROLES_COLLECTION)]

    def get_role(self, email: str) -> Optional[RoleEntry]:
        doc = FirestoreClient.get_document(ROLES_COLLECTION, email)
        return _role_entry(doc) if doc else None

    def create_role(self, entry: RoleEntry) -> bool:
        return FirestoreClient.create_document(ROLES_COLLECTION, entry["email"], _fields(entry))

    def save_role(self, entry: RoleEntry) -> None:
        FirestoreClient.upsert_document(ROLES_COLLECTION, entry["email"], _fields(entry))

    def update_role(self, email: str, fields: Dict[str, Any]) -> None:  # Any: values of RoleEntry fields
        FirestoreClient.update_fields(ROLES_COLLECTION, email, fields)

    def delete_role(self, email: str) -> None:
        FirestoreClient.delete_document(ROLES_COLLECTION, email)

    def list_requests(self) -> List[AccessRequestEntry]:
        return [_request_entry(doc) for doc in FirestoreClient.list_documents(REQUESTS_COLLECTION)]

    def get_request(self, email: str) -> Optional[AccessRequestEntry]:
        doc = FirestoreClient.get_document(REQUESTS_COLLECTION, email)
        return _request_entry(doc) if doc else None

    def save_request(self, entry: AccessRequestEntry) -> None:
        FirestoreClient.upsert_document(REQUESTS_COLLECTION, entry["email"], _fields(entry))

    def delete_request(self, email: str) -> None:
        FirestoreClient.delete_document(REQUESTS_COLLECTION, email)

    def add_history(self, entry: HistoryEntry) -> None:
        # Id: the date first (readable in the console), then a random part (two changes in the same second)
        FirestoreClient.upsert_document(HISTORY_COLLECTION, f"{entry['at']}-{uuid.uuid4().hex[:8]}", _fields(entry))

    def list_history(self) -> List[HistoryEntry]:
        return [_history_entry(doc) for doc in FirestoreClient.list_documents(HISTORY_COLLECTION)]
