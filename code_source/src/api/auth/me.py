"""GET /api/me: the signed-in account and its role, as decided by api_auth.

The pages show the role from this answer instead of keeping their own copy of the access list. As a side effect, the
answer records the last sign-in date of a listed person, or an access request for a verified address without access
(Administration › Accès). Those writes never fail the answer."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.responses import error, error_responses
from infrastructure.security.api_auth import ACCESS_UNAVAILABLE_MESSAGE, emulator_claims, role_for_claims, verified_email
from infrastructure.security.role_directory import AccessUnavailable
from infrastructure.security.roles import ROLE_NAMES, Role, RoleName
from services.access import rules as access_rules

logger = logging.getLogger("alj")

router = APIRouter(prefix="/api/me")


class Me(BaseModel):
    email: str
    role: Optional[RoleName]  # None: signed in, but no access to the club's data


def signed_in_claims(request: Request) -> Optional[Dict[str, Any]]:  # Any: the token's claims
    """Verified by auth_middleware when token checks are on; the emulator's token in dev mode."""
    return getattr(request.state, "user", None) or emulator_claims(request.headers.get("authorization"))


def _record_sign_in(claims: Dict[str, Any], role: Optional[Role]) -> None:  # Any: the token's claims
    email = verified_email(claims)
    if not email:
        return
    try:
        rules = access_rules.current()
        if role is None:
            rules.record_refused_sign_in(email, str(claims.get("name") or ""))
        else:
            rules.record_sign_in(email)
    except Exception:
        logger.warning("Connexion de %s non enregistrée dans la liste des accès", email, exc_info=True)


@router.get("", response_model=Me, responses={401: {"description": "Not signed in"}, **error_responses(503)})
def get_me(request: Request) -> Me | JSONResponse:
    claims = signed_in_claims(request)
    if not claims:
        return error(401, "Authentification requise : connectez-vous avec votre compte Google")
    try:
        role = role_for_claims(claims)
    except AccessUnavailable:
        return error(503, ACCESS_UNAVAILABLE_MESSAGE, "access_unavailable")
    _record_sign_in(claims, role)
    return Me(email=str(claims.get("email") or ""), role=ROLE_NAMES[role] if role else None)
