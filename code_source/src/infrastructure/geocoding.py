"""Address geocoding (Nominatim / OpenStreetMap), cached in the SQLite geocache table."""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

import requests

from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.sqlite.geocache import GeocacheRepository

logger = logging.getLogger("alj")

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires an identifying User-Agent and at most one request per second
NOMINATIM_USER_AGENT = "alj_escalade_manager"
NOMINATIM_PAUSE_SECONDS = 1.5
NOMINATIM_TIMEOUT_SECONDS = 10


def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """(latitude, longitude) of the best Nominatim match, or None when the address is not found.

    Raises `requests.RequestException` on a network or HTTP failure.
    """
    response = requests.get(
        NOMINATIM_SEARCH_URL,
        params={"q": address, "format": "jsonv2", "limit": "1"},
        headers={"User-Agent": NOMINATIM_USER_AGENT},
        timeout=NOMINATIM_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


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
