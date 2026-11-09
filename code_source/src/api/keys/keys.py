"""Club keys (Outils › Clés): coaches read, admins write (api_auth.required_role)."""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Request

from api.auth.me import author_of
from api.keys.schemas import Key, KeyAssignmentIn, KeyDone, KeyIn, KeyReturnIn
from api.responses import SUCCESS, error_responses
from infrastructure.sqlite.keys import KeyRow
from services.keys import club_keys
from services.keys.club_keys import KeyService

router = APIRouter(prefix="/api/keys")


@router.get("", response_model=List[Key])
def list_keys() -> List[club_keys.Key]:
    return KeyService.list_keys()


@router.post("", status_code=201, response_model=Key, responses=error_responses(409))
def add_key(body: KeyIn) -> KeyRow:
    return KeyService.add_key(body.code)


@router.post("/{key_id}/assignments", response_model=KeyDone, responses=error_responses(404, 409))
def assign_key(request: Request, key_id: int, body: KeyAssignmentIn) -> Dict[str, str]:
    KeyService.assign(key_id, body.user_id, body.given_on.isoformat(), body.comment, author_of(request))
    return SUCCESS


@router.post("/{key_id}/return", response_model=KeyDone, responses=error_responses(400, 404, 409))
def return_key(key_id: int, body: KeyReturnIn) -> Dict[str, str]:
    KeyService.give_back(key_id, body.returned_on.isoformat(), body.comment)
    return SUCCESS
