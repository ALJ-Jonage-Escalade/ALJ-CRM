"""Members map of the Outils page: members of a season grouped by geocoded address, from the SQLite cache, and the
geocoding of the addresses missing from the geocache."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import requests

from domain.members.view import is_cancelled
from domain.utils import clean_city_name
from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.geocoding.nominatim import NOMINATIM_PAUSE_SECONDS, geocode_address
from infrastructure.sqlite.geocache import GeocacheRepository
from infrastructure.sqlite.members import MemberRepository

logger = logging.getLogger("alj")


@dataclass(frozen=True)
class MapMemberEntry:
    name: str
    group: str


@dataclass
class MemberMapPoint:
    address: str
    lat: float
    lon: float
    members: List[MapMemberEntry] = field(default_factory=list)


@dataclass
class MemberMap:
    """points: the geocoded addresses; missing_addresses: the ones not in the geocache yet (sorted), to geocode."""
    points: List[MemberMapPoint]
    missing_addresses: List[str]


def member_map(season: Optional[str]) -> MemberMap:
    """Members of the season (None: every season), cancelled ones left out, grouped by geocoded address. A member of
    several seasons is listed once per point and group; an address geocoding found nothing for is left out."""
    geocache = GeocacheRepository.get_geocache()
    points: Dict[str, MemberMapPoint] = {}
    seen: Set[Tuple[str, MapMemberEntry]] = set()
    missing_addresses: Set[str] = set()

    for row in MemberRepository.list_flat_member_rows(season):
        if is_cancelled(row.get("status")):
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
            point = MemberMapPoint(address=f"{street}, {zip_code} {city}" if street else city, lat=lat, lon=lon)
            points[key] = point
        first_name = str(row.get("first_name") or "").strip().title()
        last_name = str(row.get("last_name") or "").strip().upper()
        member = MapMemberEntry(name=f"{first_name} {last_name}".strip(), group=str(row.get("tarif_name") or "").strip() or "Aucun")
        if (key, member) not in seen:
            seen.add((key, member))
            point.members.append(member)

    for point in points.values():
        point.members.sort(key=lambda m: (m.name, m.group))
    return MemberMap(points=list(points.values()), missing_addresses=sorted(missing_addresses))


def geocode_missing_addresses(addresses: List[str]) -> None:
    """Geocode the addresses missing from the cache, in the background, one request every 1.5 s."""
    found_count = 0
    for index, address in enumerate(addresses, start=1):
        time.sleep(NOMINATIM_PAUSE_SECONDS)
        try:
            coordinates = geocode_address(address)
        except (requests.RequestException, KeyError, ValueError) as exc:
            # Members' addresses and coordinates are personal data: never in the logs
            logger.warning("Geocoding failed for address %d/%d: %s", index, len(addresses), type(exc).__name__)
            continue
        if coordinates:
            found_count += 1
            GeocacheRepository.save_geocode(address, coordinates[0], coordinates[1])
        else:
            # Empty coordinates so that an unknown address is not requested again
            GeocacheRepository.save_geocode(address, None, None)
    if CloudDatabase.is_enabled():
        CloudDatabase.flush_only()
    logger.info("Geocoding done: %d of %d addresses found", found_count, len(addresses))
