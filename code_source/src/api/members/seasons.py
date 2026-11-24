"""Membership seasons and their HelloAsso tariffs (coach)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.members.schemas import Seasons, SeasonTarifs
from api.responses import error_responses, json_with_etag
from services.members.seasons import SeasonService as Service
from domain.constants import resolve_season
from infrastructure.sqlite.seasons import SeasonRepository

# No prefix: the tariffs route predates /api/seasons and keeps its URL (/api/season-tarifs)
router = APIRouter()


@router.get("/api/seasons", response_model=Seasons)
def list_seasons(request: Request) -> Response:
    return json_with_etag(request, Service.list_seasons())


@router.get("/api/season-tarifs", response_model=SeasonTarifs, responses=error_responses(400, 500))
def get_season_tarifs_api(season: Optional[str] = None) -> SeasonTarifs:
    """Retourne la liste des tarifs HelloAsso (groupes disponibles) d'une saison pour l'édition de créneau."""
    target_season = resolve_season(season)
    tarifs = SeasonRepository.get_season_tarifs(target_season)
    return SeasonTarifs(status="success", season=target_season, tarifs=tarifs)
