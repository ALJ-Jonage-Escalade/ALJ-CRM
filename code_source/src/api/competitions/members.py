"""Members as seen by the competition pages (read-only projection)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from api.competitions.schemas.views import CompetitionMember
from api.members.schemas import MemberStatus
from api.responses import json_with_etag
from services.competitions.members import CompetitionMemberService as Service

router = APIRouter(prefix="/api/competition-members")


@router.get("", response_model=List[CompetitionMember])
def list_competition_members(
    request: Request,
    status: Optional[List[MemberStatus]] = Query(None, description="Only the members at one of these statuses (repeatable)"),
) -> Response:
    return json_with_etag(request, Service.list_members(list(status) if status else None))
