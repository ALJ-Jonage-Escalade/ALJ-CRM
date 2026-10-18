"""Member list of the web pages, one season per call, and the competitors' contacts kept
offline by the phone (coach).

Member writes stay on the existing routes (/api/members/update, /api/attestations/*).
"""

from typing import Optional

from fastapi import APIRouter, Request

from api.responses import json_with_etag
from services.member_service import MemberService as Service

router = APIRouter(prefix="/api/members")


@router.get("")
def list_members(request: Request, season: Optional[str] = None):
    return json_with_etag(request, Service.list_members(season))


@router.get("/competitors")
def list_competitors(request: Request):
    return json_with_etag(request, Service.list_competitors())
