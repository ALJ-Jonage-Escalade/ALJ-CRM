"""Membership seasons (coach)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.responses import json_with_etag
from services.members.seasons import SeasonService as Service

router = APIRouter(prefix="/api/seasons")


@router.get("")
def list_seasons(request: Request) -> Response:
    return json_with_etag(request, Service.list_seasons())
