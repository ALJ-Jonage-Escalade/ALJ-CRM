"""Members as seen by the competition pages (read-only projection)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.responses import json_with_etag
from services.competitions.members import CompetitionMemberService as Service

router = APIRouter(prefix="/api/competition-members")


@router.get("")
def list_competition_members(request: Request) -> Response:
    return json_with_etag(request, Service.list_members())
