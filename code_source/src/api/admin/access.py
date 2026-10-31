"""Administration › Accès: who may use the CRM and with which role, the invitations and the history.

Admins only on every method (api_auth.required_role). Firestore only (server.py FIRESTORE_ONLY_PATHS): never waits for
the SQLite cache. Refusals: 400 (invalid e-mail or role), 404 (unknown entry), 409 (already listed or invited, nothing
to resend, an admin removing or demoting themselves, the last admin), with French messages shown as they are by the page.
"""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Request

from api.admin.schemas import AccessDone, AccessEntry, AccessEntryIn, AccessEntryPatch, AccessHistoryEntry, AccessInvitation
from api.auth.me import signed_in_claims
from api.responses import SUCCESS, error_responses
from infrastructure.firestore.access_store import HistoryEntry, RoleEntry
from services.access import invitations
from services.access import rules as access_rules

router = APIRouter(prefix="/api/admin/access")

LOCAL_AUTHOR = "serveur local"


def page_origin(request: Request) -> str:
    """Where the admin's page is served (the browser's Origin), for the link of an invitation without APP_PUBLIC_URL;
    the server's address when there is none (Cloud Run's base URL says http, behind its proxy)."""
    origin = request.headers.get("origin", "")
    return origin if origin.startswith(("https://", "http://")) else str(request.base_url)


def author_of(request: Request) -> str:
    """E-mail of the admin making the change (the local server without token checks has none)."""
    claims = signed_in_claims(request)
    return str((claims or {}).get("email") or LOCAL_AUTHOR).strip().lower()


@router.get("/roles", response_model=List[AccessEntry])
def list_roles() -> List[RoleEntry]:
    return access_rules.current().list_roles()


@router.post("/roles", status_code=201, response_model=AccessInvitation, responses=error_responses(400, 409))
def invite(request: Request, body: AccessEntryIn) -> invitations.Invitation:
    return invitations.invite(access_rules.current(), author_of(request), body.email, body.role, body.display_name,
                              page_origin(request))


@router.post("/roles/{email}/invitation", response_model=AccessInvitation, responses=error_responses(404, 409))
def resend_invitation(request: Request, email: str) -> invitations.Invitation:
    return invitations.resend(access_rules.current(), author_of(request), email, page_origin(request))


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


@router.get("/history", response_model=List[AccessHistoryEntry])
def history() -> List[HistoryEntry]:
    return access_rules.current().history()
