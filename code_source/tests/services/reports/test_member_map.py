"""Geocoding of the addresses missing from the geocache (services/reports/member_map.py), Nominatim stubbed."""

from __future__ import annotations

from unittest.mock import patch

import requests

from services.reports import member_map


def test_geocode_missing_addresses_caches_results_and_skips_failures() -> None:
    answers = [(1.0, 2.0), None, requests.ConnectionError("down")]
    with patch.object(member_map, "geocode_address", side_effect=answers), \
         patch.object(member_map.time, "sleep"), \
         patch.object(member_map.GeocacheRepository, "save_geocode") as save, \
         patch.object(member_map.CloudDatabase, "is_enabled", return_value=False):
        member_map.geocode_missing_addresses(["a", "b", "c"])
    assert [call.args for call in save.call_args_list] == [("a", 1.0, 2.0), ("b", None, None)]
