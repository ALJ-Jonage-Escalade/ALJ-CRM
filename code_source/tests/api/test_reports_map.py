"""GET /api/reports/map-points (src/api/reports/map.py): members of a season grouped by geocoded address, the
addresses missing from the geocache handed to the background geocoding (auth off, local server)."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from infrastructure.security.api_auth import Role, required_role

import server

HOME = "1 rue des Lilas, 69330, JONAGE, France"
UNKNOWN = "9 impasse Inconnue, 69330, JONAGE, France"
GEOCACHE = {HOME: [45.795, 5.045], "MEYZIEU, 69330, France": [45.77, 5.0], UNKNOWN: [None, None]}


def _row(first_name, last_name, tarif="Loisir", address="1 rue des Lilas", city="Jonage", status="Validé"):
    return {"first_name": first_name, "last_name": last_name, "tarif_name": tarif, "address": address,
            "city": city, "zip_code": "69330", "status": status}


@pytest.fixture
def client():
    with patch.dict(os.environ, {"ALJ_API_AUTH": "off"}):
        yield TestClient(server.app)


def _get(client, rows, season="active"):
    with patch("infrastructure.sqlite.members.MemberRepository.load_direct_data", return_value=rows) as load, \
         patch("infrastructure.sqlite.geocache.GeocacheRepository.get_geocache", return_value=GEOCACHE), \
         patch("api.reports.map.geocode_missing_addresses") as geocode, \
         patch("api.reports.get_active_season", return_value="2026-2027"):
        response = client.get("/api/reports/map-points", params={"season": season})
    return response, load, geocode


def test_map_points_grouped_by_address(client):
    rows = [_row("ron", "weasley"), _row("Ginny", "Weasley", tarif="Compet"),
            _row("Luna", "Lovegood", address="", city="Meyzieu", tarif="")]
    response, load, geocode = _get(client, rows)

    assert response.status_code == 200
    body = response.json()
    assert body["season"] == "2026-2027"
    load.assert_called_once_with("2026-2027")
    assert body["points"] == [
        {"address": "1 rue des Lilas, 69330 JONAGE", "lat": 45.795, "lon": 5.045,
         "members": [{"name": "Ginny WEASLEY", "group": "Compet"}, {"name": "Ron WEASLEY", "group": "Loisir"}]},
        {"address": "MEYZIEU", "lat": 45.77, "lon": 5.0, "members": [{"name": "Luna LOVEGOOD", "group": "Aucun"}]},
    ]
    geocode.assert_not_called()


def test_map_points_skip_cancelled_and_unplaced_members(client):
    rows = [_row("Ron", "Weasley", status="Annulé"), _row("Ginny", "Weasley", status="Refunded"), _row("Neville", "Londubat", city=""),
            _row("Harry", "Potter", address="4 Privet Drive"),
            _row("Drago", "Malefoy", address="9 impasse Inconnue")]  # not found by the geocoding: not retried
    response, _, geocode = _get(client, rows)

    assert response.json()["points"] == []
    geocode.assert_called_once_with(["4 Privet Drive, 69330, JONAGE, France"])


def test_map_points_every_season_lists_a_member_once(client):
    rows = [_row("Ron", "Weasley"), _row("Ron", "Weasley"), _row("Ron", "Weasley", tarif="Compet")]
    response, load, _ = _get(client, rows, season="Toutes les saisons")

    load.assert_called_once_with("Toutes les saisons")
    assert response.json()["points"][0]["members"] == [{"name": "Ron WEASLEY", "group": "Compet"},
                                                       {"name": "Ron WEASLEY", "group": "Loisir"}]


def test_map_points_failure_is_a_generic_error(client):
    with patch("infrastructure.sqlite.members.MemberRepository.load_direct_data", side_effect=RuntimeError("disk")), \
         patch("infrastructure.sqlite.geocache.GeocacheRepository.get_geocache", return_value=GEOCACHE):
        response = client.get("/api/reports/map-points")
    assert response.status_code == 500
    assert response.json()["status"] == "error"
    assert "disk" not in response.text


def test_map_points_need_the_coach_role():
    assert required_role("GET", "/api/reports/map-points") == Role.COACH
