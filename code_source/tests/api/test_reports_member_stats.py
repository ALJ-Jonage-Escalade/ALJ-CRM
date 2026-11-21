"""GET /api/reports/member-stats (src/api/reports/member_stats.py): every season's purchases as anonymous rows for the
charts of Outils › Statistiques (auth off, local server)."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import server


def _row(**fields):
    row = {"user_id": 7, "last_name": "weasley ", "first_name": "ron", "sex": "H", "birth_date": "2000-01-15",
           "city": "jonage", "tarif_name": "Adulte", "status": "Processed", "season_name": "2026-2027",
           "already_member": 1, "order_date": "2026-06-03 10:12:00"}
    row.update(fields)
    return row


@pytest.fixture
def client():
    with patch.dict(os.environ, {"ALJ_API_AUTH": "off"}):
        yield TestClient(server.app)


def _get(client, rows):
    with patch("infrastructure.sqlite.members.MemberRepository.list_flat_member_rows", return_value=rows) as load:
        response = client.get("/api/reports/member-stats")
    return response, load


def test_member_stats_reads_every_season_without_names(client):
    response, load = _get(client, [_row()])

    assert response.status_code == 200
    load.assert_called_once_with(None)
    assert response.json() == {"records": [{
        "user_id": 7, "sex": "H", "age": 26, "age_band": "25 à 29 ans", "city": "Jonage", "group": "Adulte",
        "status": "Validé", "season": "2026-2027", "returning": True, "order_month": "2026-06",
    }]}


def test_member_stats_unknown_values(client):
    row = _row(sex=None, birth_date=None, city=None, tarif_name="", status="Cancelled", season_name=None,
               already_member=None, order_date="03/06/2026")
    record = _get(client, [row])[0].json()["records"][0]

    assert record == {
        "user_id": 7, "sex": None, "age": None, "age_band": "Inconnue", "city": "Inconnue", "group": "Aucun",
        "status": "Annulé", "season": "Inconnue", "returning": False, "order_month": "Inconnue",
    }
