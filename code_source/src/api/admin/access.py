"""Administration › Accès: who may use the CRM and with which role, the access requests and the history.

Admins only on every method (api_auth.required_role). Firestore only (server.py FIRESTORE_ONLY_PATHS): never waits for
the SQLite cache. Refusals: 400 (invalid e-mail or role), 404 (unknown entry or request), 409 (already listed, an admin
removing or demoting themselves, the last admin), with French messages shown as they are by the page.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Request

from api.admin.schemas import AccessDone, AccessEntry, AccessEntryIn, AccessEntryPatch, AccessGrant, AccessHistoryEntry, AccessRequest
from api.auth.me import signed_in_claims
from api.responses import SUCCESS, error_responses
from infrastructure.firestore.access_store import AccessRequestEntry, HistoryEntry, RoleEntry
from services.access import rules as access_rules

router = APIRouter(prefix="/api/admin/access")

LOCAL_AUTHOR = "serveur local"


def author_of(request: Request) -> str:
    """E-mail of the admin making the change (the local server without token checks has none)."""
    claims = signed_in_claims(request)
    return str((claims or {}).get("email") or LOCAL_AUTHOR).strip().lower()


def _request_body(request: AccessRequestEntry) -> Dict[str, Any]:  # Any: an AccessRequest body
    return {k: v for k, v in request.items() if k != "dismissed_at"}


@router.get("/roles", response_model=List[AccessEntry])
def list_roles() -> List[RoleEntry]:
    return access_rules.current().list_roles()


@router.post("/roles", status_code=201, response_model=AccessEntry, responses=error_responses(400, 409))
def add_role(request: Request, body: AccessEntryIn) -> RoleEntry:
    return access_rules.current().grant(author_of(request), body.email, body.role, body.display_name)


@router.patch("/roles/{email}", response_model=AccessEntry, responses=error_responses(400, 404, 409))
def update_role(request: Request, email: str, body: AccessEntryPatch) -> RoleEntry:
    rules = access_rules.current()
    author = author_of(request)
    entry = rules.entry_of(email)
    # Role first: a refused role change (409) leaves the name unchanged too
    if body.role is not None:
        entry = rules.change_role(author, email, body.role)
    if body.display_name is not None:
        entry = rules.rename(author, email, body.display_name)
    return entry


@router.delete("/roles/{email}", response_model=AccessDone, responses=error_responses(404, 409))
def remove_role(request: Request, email: str) -> Dict[str, str]:
    access_rules.current().remove(author_of(request), email)
    return SUCCESS


@router.get("/requests", response_model=List[AccessRequest])
def list_requests() -> List[Dict[str, Any]]:  # Any: AccessRequest bodies
    return [_request_body(r) for r in access_rules.current().list_requests()]


@router.post("/requests/{email}/grant", status_code=201, response_model=AccessEntry, responses=error_responses(400, 404, 409))
def grant_request(request: Request, email: str, body: AccessGrant) -> RoleEntry:
    return access_rules.current().grant_request(author_of(request), email, body.role, body.display_name)


@router.delete("/requests/{email}", response_model=AccessDone, responses=error_responses(404))
def dismiss_request(request: Request, email: str) -> Dict[str, str]:
    access_rules.current().dismiss_request(author_of(request), email)
    return SUCCESS


@router.get("/history", response_model=List[AccessHistoryEntry])
def history() -> List[HistoryEntry]:
    return access_rules.current().history()
