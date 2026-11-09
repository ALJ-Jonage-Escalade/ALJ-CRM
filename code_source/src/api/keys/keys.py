"""Club keys (Outils › Clés): coaches read, admins write (api_auth.required_role)."""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Request

from api.auth.me import author_of
from api.keys.schemas import Key, KeyAssignmentIn, KeyAssignmentPatch, KeyDone, KeyHistory, KeyIn, KeyRename, KeyReturnIn
from api.responses import SUCCESS, error_responses
from infrastructure.sqlite.keys import KeyRow
from services.keys import club_keys
from services.keys.club_keys import KeyService

router = APIRouter()


@router.get("/api/keys", response_model=List[Key])
def list_keys() -> List[club_keys.Key]:
    return KeyService.list_keys()


@router.post("/api/keys", status_code=201, response_model=Key, responses=error_responses(409))
def add_key(body: KeyIn) -> KeyRow:
    return KeyService.add_key(body.code)


@router.post("/api/keys/{key_id}/assignments", response_model=KeyDone, responses=error_responses(404, 409))
def assign_key(request: Request, key_id: int, body: KeyAssignmentIn) -> Dict[str, str]:
    KeyService.assign(key_id, body.user_id, body.given_on.isoformat(), body.comment, author_of(request))
    return SUCCESS


@router.post("/api/keys/{key_id}/return", response_model=KeyDone, responses=error_responses(400, 404, 409))
def return_key(key_id: int, body: KeyReturnIn) -> Dict[str, str]:
    KeyService.give_back(key_id, body.returned_on.isoformat(), body.comment)
    return SUCCESS


@router.patch("/api/keys/{key_id}", response_model=KeyDone, responses=error_responses(404, 409))
def rename_key(request: Request, key_id: int, body: KeyRename) -> Dict[str, str]:
    KeyService.rename(key_id, body.code, author_of(request))
    return SUCCESS


@router.get("/api/keys/{key_id}/history", response_model=KeyHistory, responses=error_responses(404))
def key_history(key_id: int) -> List[club_keys.HistoryEntry]:
    return KeyService.history(key_id)


@router.patch("/api/key-assignments/{assignment_id}", response_model=KeyDone, responses=error_responses(400, 404))
def correct_assignment(assignment_id: int, body: KeyAssignmentPatch) -> Dict[str, str]:
    KeyService.correct_assignment(assignment_id, body.given_on.isoformat(), body.returned_on.isoformat() if body.returned_on else None,
                                  body.comment, body.return_comment)
    return SUCCESS


@router.delete("/api/key-assignments/{assignment_id}", response_model=KeyDone, responses=error_responses(404, 409))
def delete_assignment(request: Request, assignment_id: int) -> Dict[str, str]:
    KeyService.delete_assignment(assignment_id, author_of(request))
    return SUCCESS
