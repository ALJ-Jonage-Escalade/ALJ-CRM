"""Who may use the CRM: the access list and its history, in Firestore.

Two collections, read and written by the server only (firestore.rules refuses every client). No `crm_`
prefix: they are not copied into the SQLite cache.
- `access_roles`: one document per normalised e-mail (its id), with the role. The only source of roles. An invited
  person's entry also holds the invitation dates (services/access/rules.py).
- `access_history`: write-once entries, one per change.

Dates are ISO 8601 strings in UTC (`2026-10-30T09:15:00+00:00`): they sort as text.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Literal, Optional, Protocol, TypedDict, TypeGuard, get_args

from infrastructure.firestore.client import META_KEYS, FirestoreClient
from infrastructure.security.roles import RoleName, is_role_name

logger = logging.getLogger("alj")

ROLES_COLLECTION = "access_roles"
HISTORY_COLLECTION = "access_history"


class RoleEntry(TypedDict):
    email: str
    role: RoleName
    display_name: str
    last_sign_in_at: Optional[str]
    created_at: Optional[str]
    created_by: Optional[str]
    updated_at: Optional[str]
    updated_by: Optional[str]
    invited_at: Optional[str]
    invitation_expires_at: Optional[str]  # null: no pending invitation (accepted, or an entry added before invitations)
    invitation_sent_at: Optional[str]  # null: the invitation e-mail could not be sent
    accepted_at: Optional[str]


# "added": an entry created before invitations existed
HistoryAction = Literal["invited", "invitation_resent", "added", "role_changed", "name_changed", "removed", "bootstrap"]


def is_history_action(value: object) -> TypeGuard[HistoryAction]:
    return value in get_args(HistoryAction)


class HistoryEntry(TypedDict):
    at: str
    author: str  # e-mail of the admin, or "bootstrap"
    action: HistoryAction
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
    def add_history(self, entry: HistoryEntry) -> None: ...
    def list_history(self, limit: int) -> List[HistoryEntry]:
        """The `limit` latest entries, latest first."""
        ...


def _role_entry(doc: Dict[str, Any]) -> Optional[RoleEntry]:  # Any: a Firestore document
    """The entry of a stored document; None for a role this version does not know (edited by hand in the console),
    which gives no access either way."""
    role = doc.get("role")
    if not is_role_name(role):
        logger.warning("Access list: entry %s has an unknown role, left out", doc.get("_doc_id") or doc.get("email"))
        return None
    return RoleEntry(
        email=str(doc.get("email") or doc.get("_doc_id") or ""),
        role=role,
        display_name=str(doc.get("display_name") or ""),
        last_sign_in_at=doc.get("last_sign_in_at"),
        created_at=doc.get("created_at"),
        created_by=doc.get("created_by"),
        updated_at=doc.get("updated_at"),
        updated_by=doc.get("updated_by"),
        invited_at=doc.get("invited_at"),
        invitation_expires_at=doc.get("invitation_expires_at"),
        invitation_sent_at=doc.get("invitation_sent_at"),
        accepted_at=doc.get("accepted_at"),
    )


def _history_entry(doc: Dict[str, Any]) -> Optional[HistoryEntry]:  # Any: a Firestore document
    action = doc.get("action")
    if not is_history_action(action):
        logger.warning("Access history: entry %s has an unknown action, left out", doc.get("_doc_id"))
        return None
    return HistoryEntry(
        at=str(doc.get("at") or ""),
        author=str(doc.get("author") or ""),
        action=action,
        target_email=str(doc.get("target_email") or ""),
        old_role=doc.get("old_role"),
        new_role=doc.get("new_role"),
    )


def _fields(entry: Any) -> Dict[str, Any]:  # Any: one of the TypedDicts above
    return {k: v for k, v in dict(entry).items() if k not in META_KEYS}


class FirestoreAccessStore:
    """AccessStore on the project's Firestore database (through FirestoreClient)."""

    def list_roles(self) -> List[RoleEntry]:
        entries = (_role_entry(doc) for doc in FirestoreClient.list_documents(ROLES_COLLECTION))
        return [entry for entry in entries if entry is not None]

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

    def add_history(self, entry: HistoryEntry) -> None:
        # Id: the date first (readable in the console), then a random part (two changes in the same second)
        FirestoreClient.upsert_document(HISTORY_COLLECTION, f"{entry['at']}-{uuid.uuid4().hex[:8]}", _fields(entry))

    def list_history(self, limit: int) -> List[HistoryEntry]:
        entries = (_history_entry(doc) for doc in FirestoreClient.list_latest(HISTORY_COLLECTION, "at", limit))
        return [entry for entry in entries if entry is not None]
