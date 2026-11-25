"""Address geocoding with Nominatim (OpenStreetMap). The results are cached by services.reports.member_map."""

from __future__ import annotations

from typing import Optional, Tuple

import requests

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
