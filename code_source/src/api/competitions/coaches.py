"""Coaches (a rename or a delete also updates their competitions)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.responses import STORAGE_ERRORS, SUCCESS, error_responses, json_with_etag
from api.competitions.schemas.coaches import CoachIn
from api.competitions.schemas.views import Coach, Done
from services.competitions.coaches import CoachService as Service
from services.documents import Doc

router = APIRouter(prefix="/api/coaches")


@router.get("", response_model=List[Coach], responses=error_responses(*STORAGE_ERRORS))
def list_coaches(request: Request) -> Response:
    return json_with_etag(request, Service.list_coaches())


@router.post("", status_code=201, response_model=Coach, responses=error_responses(*STORAGE_ERRORS))
def create_coach(body: CoachIn) -> Doc:
    return {"id": Service.create_coach(body.nom), "nom": body.nom}


@router.put("/{coach_id}", response_model=Coach, responses=error_responses(404, *STORAGE_ERRORS))
def update_coach(coach_id: int, body: CoachIn) -> Doc:
    Service.rename_coach(coach_id, body.nom)
    return {"id": coach_id, "nom": body.nom}


@router.delete("/{coach_id}", response_model=Done, responses=error_responses(404, *STORAGE_ERRORS))
def delete_coach(coach_id: int) -> Doc:
    Service.delete_coach(coach_id)
    return SUCCESS
