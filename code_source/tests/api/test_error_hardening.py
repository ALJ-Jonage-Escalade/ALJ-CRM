"""Request values never reach file paths unchecked, and exception details (SQL, paths,
third-party messages) stay in the server log instead of the JSON responses (CodeQL
py/path-injection and py/stack-trace-exposure)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from domain.constants import is_valid_season
from domain.errors import UpstreamUnavailable
from infrastructure.sqlite.connection import DB_WRITE_ERROR, SqliteDatabase
from infrastructure.sqlite.members import MemberRepository

SECRET_DETAIL = "sqlite3 at /srv/app/data/database.db: no such table"
BAD_SEASONS = ["../../etc/x", "2026-2027/../../x", "2026-2027\r\nSet-Cookie: a=b", "x" * 9]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ALJ_API_AUTH", "off")
    from server import app
    return TestClient(app)


@pytest.mark.parametrize("season", ["2026-2027", "1999-2000"])
def test_is_valid_season_accepts_season_format(season: str) -> None:
    assert is_valid_season(season)


@pytest.mark.parametrize("season", BAD_SEASONS + ["", "2026", "2026-27", " 2026-2027"])
def test_is_valid_season_rejects_other_values(season: str) -> None:
    assert not is_valid_season(season)


@pytest.mark.parametrize("season", BAD_SEASONS)
def test_planning_export_rejects_bad_season(client: TestClient, season: str) -> None:
    resp = client.get("/api/planning/export", params={"season": season})
    assert resp.status_code == 400
    assert "Saison invalide" in resp.json()["message"]


@pytest.mark.parametrize("season", BAD_SEASONS)
def test_presence_export_rejects_bad_season(client: TestClient, season: str) -> None:
    resp = client.post("/api/presence/export", json={"season": season})
    assert resp.status_code == 400
    assert "Saison invalide" in resp.json()["message"]


def test_presence_export_error_is_generic(client: TestClient) -> None:
    with patch("infrastructure.sqlite.members.MemberRepository.load_direct_data", side_effect=RuntimeError(SECRET_DETAIL)):
        body = client.post("/api/presence/export", json={}).json()
    assert SECRET_DETAIL not in str(body)
    assert "journaux" in body["message"]


def test_cloud_db_sync_returns_counters_only(client: TestClient) -> None:
    report = {"pulled": 3, "pushed": 1, "full": True, "errors": [SECRET_DETAIL]}
    with patch("infrastructure.firestore.cloud_database.CloudDatabase.is_enabled", return_value=True), \
            patch("infrastructure.firestore.cloud_database.CloudDatabase.sync", return_value=report):
        resp = client.post("/api/cloud-db/sync")
    assert resp.status_code == 500
    body = resp.json()
    assert SECRET_DETAIL not in str(body)
    assert body["result"] == {"pulled": 3, "pushed": 1, "full": True}


def test_cloud_db_status_hides_last_error(client: TestClient) -> None:
    status = {"pending": 0, "last_error": SECRET_DETAIL, "last_sync": None}
    with patch("infrastructure.firestore.cloud_database.CloudDatabase.is_enabled", return_value=True), \
            patch("infrastructure.firestore.cloud_database.CloudDatabase.status", return_value=status):
        body = client.get("/api/cloud-db/status").json()
    assert SECRET_DETAIL not in str(body)
    assert body["last_error"]  # still truthy: the page knows the last sync failed


def test_repository_write_error_is_generic() -> None:
    conn = MagicMock()
    conn.cursor.return_value.execute.side_effect = RuntimeError(SECRET_DETAIL)
    with patch.object(SqliteDatabase, "setup_database"), patch.object(SqliteDatabase, "get_connection", return_value=conn):
        ok, message = MemberRepository.update_member_fields(user_id=1, fields={"phone": "0600000000"})
    assert not ok
    assert message == DB_WRITE_ERROR
    conn.rollback.assert_called_once()


def test_mycompet_scraping_error_is_generic(client: TestClient) -> None:
    with patch("services.competitions.results_batch.fetch_and_parse_mycompet_results", side_effect=UpstreamUnavailable(SECRET_DETAIL)), \
            patch("infrastructure.firestore.competition_repository.CompetitionFirestoreRepository.get_stored_competition_doc",
                  return_value={"id": 1, "nom": "Open"}):
        resp = client.post("/api/competitions/1/fetch-results", json={"url": "https://mycompet.ffme.fr/resultat/resultat_1"})
    assert resp.status_code == 502
    assert SECRET_DETAIL not in resp.text
