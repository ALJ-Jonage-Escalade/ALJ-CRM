"""Nominatim geocoding (infrastructure/geocoding.py), with the HTTP call stubbed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from infrastructure import geocoding


def _response(payload: object, status_code: int = 200) -> MagicMock:
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"{status_code}")
    return response


def test_geocode_address_reads_the_first_result() -> None:
    with patch("infrastructure.geocoding.requests.get", return_value=_response([{"lat": "45.79", "lon": "5.04"}])) as get:
        assert geocoding.geocode_address("4 Privet Drive, Jonage") == (45.79, 5.04)
    assert get.call_args.kwargs["params"]["q"] == "4 Privet Drive, Jonage"
    assert get.call_args.kwargs["headers"]["User-Agent"]
    assert get.call_args.kwargs["timeout"]


def test_geocode_address_not_found() -> None:
    with patch("infrastructure.geocoding.requests.get", return_value=_response([])):
        assert geocoding.geocode_address("nowhere") is None


def test_geocode_missing_addresses_caches_results_and_skips_failures() -> None:
    answers = [(1.0, 2.0), None, requests.ConnectionError("down")]
    with patch.object(geocoding, "geocode_address", side_effect=answers), \
         patch.object(geocoding.time, "sleep"), \
         patch.object(geocoding.GeocacheRepository, "save_geocode") as save, \
         patch.object(geocoding.CloudDatabase, "is_enabled", return_value=False):
        geocoding.geocode_missing_addresses(["a", "b", "c"])
    assert [call.args for call in save.call_args_list] == [("a", 1.0, 2.0), ("b", None, None)]
