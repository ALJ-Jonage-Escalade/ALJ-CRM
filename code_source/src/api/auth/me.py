"""GET /api/me: the signed-in account and its role, as decided by api_auth.

The pages show the role from this answer instead of keeping their own copy of the role lists."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.responses import error
from infrastructure.security.api_auth import Role, emulator_claims, role_for_claims

router = APIRouter(prefix="/api/me")

RoleName = Literal["admin", "coach", "readonly"]
ROLE_NAMES: dict[Role, RoleName] = {Role.ADMIN: "admin", Role.COACH: "coach", Role.READONLY: "readonly"}


class Me(BaseModel):
    email: str
    role: Optional[RoleName]  # None: signed in, but no access to the club's data


@router.get("", response_model=Me, responses={401: {"description": "Not signed in"}})
def get_me(request: Request) -> Me | JSONResponse:
    # Verified by auth_middleware when token checks are on; the emulator's token in dev mode
    claims = getattr(request.state, "user", None) or emulator_claims(request.headers.get("authorization"))
    if not claims:
        return error(401, "Authentification requise : connectez-vous avec votre compte Google")
    role = role_for_claims(claims)
    return Me(email=str(claims.get("email") or ""), role=ROLE_NAMES[role] if role else None)
