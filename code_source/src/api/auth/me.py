"""GET /api/me: the signed-in account and its role, as decided by api_auth.

The pages show the role from this answer instead of keeping their own copy of the access list. As a side effect, the
answer accepts a pending invitation and records the last sign-in date of a listed person (Administration › Accès);
those writes never fail the answer. An address without access leaves nothing."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.responses import error, error_responses
from infrastructure.security.api_auth import ACCESS_UNAVAILABLE_MESSAGE, emulator_claims, role_for_claims, verified_email
from infrastructure.security.role_directory import AccessUnavailable
from infrastructure.security.roles import ROLE_NAMES, RoleName
from services.access import rules as access_rules

logger = logging.getLogger("alj")

router = APIRouter(prefix="/api/me")


class Me(BaseModel):
    email: str
    role: Optional[RoleName]  # None: signed in, but no access to the club's data
    invitation_expired_at: Optional[str] = None  # without a role: when this address's invitation ran out; None: never invited


def signed_in_claims(request: Request) -> Optional[Dict[str, Any]]:  # Any: the token's claims
    """Verified by auth_middleware when token checks are on; the emulator's token in dev mode."""
    return getattr(request.state, "user", None) or emulator_claims(request.headers.get("authorization"))


def _record_sign_in(email: str) -> None:
    try:
        rules = access_rules.current()
        rules.accept_invitation(email)
        rules.record_sign_in(email)
    except Exception:
        logger.warning("Connexion de %s non enregistrée dans la liste des accès", email, exc_info=True)


def _expired_invitation(email: str) -> Optional[str]:
    try:
        return access_rules.current().directory.expired_invitation_of(email)
    except Exception:  # only for the message shown: the answer stays "no access"
        logger.warning("Invitation de %s non vérifiée", email, exc_info=True)
        return None


@router.get("", response_model=Me, responses={401: {"description": "Not signed in"}, **error_responses(503)})
def get_me(request: Request) -> Me | JSONResponse:
    claims = signed_in_claims(request)
    if not claims:
        return error(401, "Authentification requise : connectez-vous avec votre compte Google")
    try:
        role = role_for_claims(claims)
    except AccessUnavailable:
        return error(503, ACCESS_UNAVAILABLE_MESSAGE, "access_unavailable")
    email = verified_email(claims)
    if not email:
        return Me(email=str(claims.get("email") or ""), role=None)
    if role is None:
        return Me(email=str(claims.get("email") or ""), role=None, invitation_expired_at=_expired_invitation(email))
    _record_sign_in(email)
    return Me(email=str(claims.get("email") or ""), role=ROLE_NAMES[role])
