"""Members map (Outils page of the Vue app), from the SQLite cache; missing addresses are geocoded in the background."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from api.reports import resolve_report_season, season_read
from api.reports.schemas import MapMember, MapPoint, MapPoints
from api.responses import error_responses
from infrastructure.geocoding import geocode_missing_addresses
from services.reports.member_map import member_map

router = APIRouter()


@router.get("/api/reports/map-points", response_model=MapPoints, responses=error_responses(400, 500))
def get_map_points(background_tasks: BackgroundTasks, season: str = "active") -> Union[MapPoints, JSONResponse]:
    """Members of a season grouped by address, for the map of the Outils page ("Toutes les saisons": every season).
    The addresses missing from the geocache are geocoded in the background: they appear on the map once geocoded."""
    target_season = resolve_report_season(season)
    result = member_map(season_read(target_season))
    if result.missing_addresses:
        background_tasks.add_task(geocode_missing_addresses, result.missing_addresses)
    points = [MapPoint(address=point.address, lat=point.lat, lon=point.lon,
                       members=[MapMember(name=member.name, group=member.group) for member in point.members])
              for point in result.points]
    return MapPoints(season=target_season, points=points)
