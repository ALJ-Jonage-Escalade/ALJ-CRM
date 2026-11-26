"""Nominatim geocoding (infrastructure/geocoding/nominatim.py), with the HTTP call stubbed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from infrastructure.geocoding import nominatim


def _response(payload: object, status_code: int = 200) -> MagicMock:
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"{status_code}")
    return response


def test_geocode_address_reads_the_first_result() -> None:
    with patch("infrastructure.geocoding.nominatim.requests.get", return_value=_response([{"lat": "45.79", "lon": "5.04"}])) as get:
        assert nominatim.geocode_address("4 Privet Drive, Jonage") == (45.79, 5.04)
    assert get.call_args.kwargs["params"]["q"] == "4 Privet Drive, Jonage"
    assert get.call_args.kwargs["headers"]["User-Agent"]
    assert get.call_args.kwargs["timeout"]


def test_geocode_address_not_found() -> None:
    with patch("infrastructure.geocoding.nominatim.requests.get", return_value=_response([])):
        assert nominatim.geocode_address("nowhere") is None
