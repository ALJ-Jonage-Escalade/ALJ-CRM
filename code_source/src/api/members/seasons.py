"""Membership seasons and their HelloAsso tariffs (coach)."""

from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from api.members.schemas import SeasonTarifs
from api.responses import error, error_responses, internal_error, json_with_etag
from services.members.seasons import SeasonService as Service

# No prefix: the tariffs route predates /api/seasons and keeps its URL (/api/season-tarifs)
router = APIRouter()


@router.get("/api/seasons")
def list_seasons(request: Request) -> Response:
    return json_with_etag(request, Service.list_seasons())


@router.get("/api/season-tarifs", response_model=SeasonTarifs, responses=error_responses(500))
def get_season_tarifs_api(season: Optional[str] = None) -> Union[SeasonTarifs, JSONResponse]:
    """Retourne la liste des tarifs HelloAsso (groupes disponibles) d'une saison pour l'édition de créneau."""
    try:
        from infrastructure.sqlite.seasons import SeasonRepository
        from domain.constants import get_active_season
        target_season = season or get_active_season()
        tarifs = SeasonRepository.get_season_tarifs(target_season)
        return SeasonTarifs(status="success", season=target_season, tarifs=tarifs)
    except Exception as e:
        return error(500, internal_error(e, "get_season_tarifs_api"))
