"""GET /api/reports/pivot-records (src/api/reports/pivot.py): the members of a season as rows of the pivot table of
the Outils page, with the French field names as keys (auth off, local server)."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.reports.pivot import age_band, iso_date, status_label
from infrastructure.security.api_auth import Role, required_role

import server


def _row(**fields):
    row = {"last_name": "weasley ", "first_name": "ron", "sex": "H", "birth_date": "2000-01-15", "city": "Jonage",
           "tarif_name": "Adulte", "status": "Processed", "season_name": "2026-2027", "already_member": 1,
           "order_date": "2026-06-03 10:12:00"}
    row.update(fields)
    return row


@pytest.fixture
def client():
    with patch.dict(os.environ, {"ALJ_API_AUTH": "off"}):
        yield TestClient(server.app)


def _get(client, rows, season="active"):
    with patch("infrastructure.sqlite.members.MemberRepository.load_direct_data", return_value=rows) as load, \
         patch("api.reports.get_active_season", return_value="2026-2027"):
        response = client.get("/api/reports/pivot-records", params={"season": season})
    return response, load


def test_pivot_records_fields(client):
    response, load = _get(client, [_row()])

    assert response.status_code == 200
    load.assert_called_once_with("2026-2027")
    assert response.json() == {"season": "2026-2027", "records": [{
        "Nom": "WEASLEY", "Prénom": "Ron", "Sexe": "H", "Âge": 26, "Tranche d'Âge": "25 à 29 ans",
        "Ville": "Jonage", "Groupe / Tarif": "Adulte", "Statut": "Validé", "Saison": "2026-2027",
        "Type d'Adhésion": "Déjà Membre", "Date d'Inscription": "2026-06-03", "Mois d'Inscription": "2026-06",
    }]}


def test_pivot_records_unknown_values(client):
    row = _row(last_name=None, first_name=None, sex=None, birth_date=None, city=None, tarif_name="", status="Cancelled",
               season_name=None, already_member=None, order_date="03/06/2026")
    record = _get(client, [row])[0].json()["records"][0]

    assert record == {
        "Nom": "", "Prénom": "", "Sexe": None, "Âge": None, "Tranche d'Âge": "Inconnue", "Ville": "Inconnue",
        "Groupe / Tarif": "Aucun", "Statut": "Annulé", "Saison": "Inconnue", "Type d'Adhésion": "Nouvelle Inscription",
        "Date d'Inscription": "Inconnue", "Mois d'Inscription": "Inconnue",
    }


def test_pivot_records_every_season_ages_each_row_at_its_season(client):
    rows = [_row(season_name="2025-2026"), _row(season_name="2026-2027")]
    response, load = _get(client, rows, season="Toutes les saisons")

    load.assert_called_once_with("Toutes les saisons")
    body = response.json()
    assert body["season"] == "Toutes les saisons"
    assert [r["Âge"] for r in body["records"]] == [25, 26]


@pytest.mark.parametrize(("status", "label"), [
    ("Processed", "Validé"), ("Terminé", "Validé"), ("traité", "Validé"), ("Registered", "Validé"), (None, "Validé"),
    ("Canceled", "Annulé"), ("annulé", "Annulé"), ("Refused", "Refusé"), ("en attente", "En Attente"),
])
def test_status_label(status, label):
    assert status_label(status) == label


@pytest.mark.parametrize(("age", "band"), [
    (None, "Inconnue"), (0, "0 à 9 ans (< 10 ans)"), (9, "0 à 9 ans (< 10 ans)"), (10, "10 à 17 ans"),
    (17, "10 à 17 ans"), (18, "18 à 24 ans"), (24, "18 à 24 ans"), (25, "25 à 29 ans"), (29, "25 à 29 ans"),
    (30, "30 à 39 ans"), (39, "30 à 39 ans"), (40, "40 à 49 ans"), (49, "40 à 49 ans"), (50, "50 à 64 ans"),
    (64, "50 à 64 ans"), (65, "65 ans et plus"), (90, "65 ans et plus"),
])
def test_age_band(age, band):
    assert age_band(age) == band


@pytest.mark.parametrize(("value", "iso"), [
    ("2026-06-03", "2026-06-03"), ("2026-06-03T10:12:00+02:00", "2026-06-03"), ("03/06/2026", ""), ("", ""), (None, ""),
])
def test_iso_date(value, iso):
    assert iso_date(value) == iso


def test_pivot_records_failure_is_a_generic_error(client):
    with patch("infrastructure.sqlite.members.MemberRepository.load_direct_data", side_effect=RuntimeError("disk")):
        response = client.get("/api/reports/pivot-records")
    assert response.status_code == 500
    assert response.json()["status"] == "error"
    assert "disk" not in response.text


def test_pivot_records_need_the_coach_role():
    assert required_role("GET", "/api/reports/pivot-records") == Role.COACH


def test_pivot_counts_a_refund_as_a_cancellation(client):
    record = _get(client, [_row(status="Refunded")])[0].json()["records"][0]

    assert record["Statut"] == "Annulé"
