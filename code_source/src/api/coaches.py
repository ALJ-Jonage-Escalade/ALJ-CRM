"""Coaches (a rename or a delete also updates their competitions)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.responses import SUCCESS, json_with_etag
from api.schemas.coaches import CoachIn
from services.competitions.coaches import CoachService as Service
from services.documents import Doc

router = APIRouter(prefix="/api/coaches")


@router.get("")
def list_coaches(request: Request) -> Response:
    return json_with_etag(request, Service.list_coaches())


@router.post("", status_code=201)
def create_coach(body: CoachIn) -> Doc:
    return {"id": Service.create_coach(body.nom), "nom": body.nom}


@router.put("/{coach_id}")
def update_coach(coach_id: int, body: CoachIn) -> Doc:
    Service.rename_coach(coach_id, body.nom)
    return {"id": coach_id, "nom": body.nom}


@router.delete("/{coach_id}")
def delete_coach(coach_id: int) -> Doc:
    Service.delete_coach(coach_id)
    return SUCCESS
