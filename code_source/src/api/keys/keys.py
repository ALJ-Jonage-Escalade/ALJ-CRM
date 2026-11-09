"""Club keys (Outils › Clés): coaches read, admins write (api_auth.required_role)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

from api.keys.schemas import Key, KeyIn
from api.responses import error_responses
from infrastructure.sqlite.keys import KeyRow
from services.keys.club_keys import KeyService

router = APIRouter(prefix="/api/keys")


@router.get("", response_model=List[Key])
def list_keys() -> List[KeyRow]:
    return KeyService.list_keys()


@router.post("", status_code=201, response_model=Key, responses=error_responses(409))
def add_key(body: KeyIn) -> KeyRow:
    return KeyService.add_key(body.code)
