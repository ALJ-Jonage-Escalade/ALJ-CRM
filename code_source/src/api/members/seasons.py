"""Membership seasons and their HelloAsso tariffs (coach)."""

from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from api.responses import internal_error, json_with_etag
from services.documents import Doc
from services.members.seasons import SeasonService as Service

# No prefix: the tariffs route predates /api/seasons and keeps its URL (/api/season-tarifs)
router = APIRouter()


@router.get("/api/seasons")
def list_seasons(request: Request) -> Response:
    return json_with_etag(request, Service.list_seasons())


@router.get("/api/season-tarifs", response_model=None)
def get_season_tarifs_api(season: Optional[str] = None) -> Union[Doc, JSONResponse]:
    """Retourne la liste des tarifs HelloAsso (groupes disponibles) d'une saison pour l'édition de créneau."""
    try:
        from infrastructure.sqlite.repository import SqliteRepository
        from domain.constants import get_active_season
        target_season = season or get_active_season()
        tarifs = SqliteRepository.get_season_tarifs(target_season)
        return {"status": "success", "season": target_season, "tarifs": tarifs}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "get_season_tarifs_api")})
