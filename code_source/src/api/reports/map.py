"""Members map (Outils page of the Vue app), from the SQLite cache; missing addresses are geocoded in the background."""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple, Union

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from api.reports.schemas import MapMember, MapPoint, MapPoints
from api.responses import error, error_responses, internal_error
from domain.constants import get_active_season
from domain.utils import clean_city_name
from infrastructure.geocoding import geocode_missing_addresses
from infrastructure.sqlite.geocache import GeocacheRepository
from infrastructure.sqlite.members import MemberRepository

router = APIRouter()


def resolve_season(season: str) -> str:
    """The season to read: "", "active" and "default" mean the active season."""
    season = (season or "").strip()
    return get_active_season() if season.lower() in ("", "active", "default") else season


def map_points(season: str, background_tasks: Optional[BackgroundTasks] = None) -> List[MapPoint]:
    """Members of the season (cancelled ones left out) grouped by geocoded address. The addresses missing from the
    geocache are handed to background_tasks for geocoding; they appear on the map once geocoded."""
    geocache = GeocacheRepository.get_geocache()
    points: Dict[str, MapPoint] = {}
    seen: Set[Tuple[str, str, str]] = set()  # (point, name, group): a member of several seasons is listed once
    missing_addresses: Set[str] = set()

    for row in MemberRepository.load_direct_data(season):
        if "annul" in str(row.get("status", "Validé")).lower():
            continue

        city = clean_city_name(row.get("city") or "").upper()
        street = str(row.get("address") or "").strip()
        zip_code = str(row.get("zip_code") or "").strip()
        if street and city:
            full_address = f"{street}, {zip_code}, {city}, France"
        elif city:
            full_address = f"{city}, {zip_code}, France"
        else:
            continue
        full_address = " ".join(full_address.split())

        coords = geocache.get(full_address)
        if coords is None:
            missing_addresses.add(full_address)
            continue
        lat, lon = coords[0], coords[1]
        if lat is None or lon is None:  # geocoding found nothing: cached as such, not retried
            continue

        key = f"{lat:.6f},{lon:.6f}"
        point = points.get(key)
        if point is None:
            point = MapPoint(address=f"{street}, {zip_code} {city}" if street else city, lat=lat, lon=lon, members=[])
            points[key] = point
        first_name = str(row.get("first_name") or "").strip().title()
        last_name = str(row.get("last_name") or "").strip().upper()
        member = MapMember(name=f"{first_name} {last_name}".strip(), group=str(row.get("tarif_name") or "").strip() or "Aucun")
        if (key, member.name, member.group) not in seen:
            seen.add((key, member.name, member.group))
            point.members.append(member)

    if missing_addresses and background_tasks is not None:
        background_tasks.add_task(geocode_missing_addresses, sorted(missing_addresses))
    for point in points.values():
        point.members.sort(key=lambda m: (m.name, m.group))
    return list(points.values())


@router.get("/api/reports/map-points", response_model=MapPoints, responses=error_responses(500))
def get_map_points(background_tasks: BackgroundTasks, season: str = "active") -> Union[MapPoints, JSONResponse]:
    """Members of a season grouped by address, for the map of the Outils page ("Toutes les saisons": every season)."""
    try:
        target_season = resolve_season(season)
        return MapPoints(season=target_season, points=map_points(target_season, background_tasks))
    except Exception as e:
        return error(500, internal_error(e, "get_map_points"))
