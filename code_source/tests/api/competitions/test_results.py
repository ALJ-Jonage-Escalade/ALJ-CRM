"""Schemas of src/api/competitions/results.py: the batch report accepts whatever the scraped data holds."""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

from api.competitions.schemas.results import BatchReport
from domain.club_emails import DEFAULT_RESULTS_NOTIFICATION_EMAIL
from domain.errors import UpstreamUnavailable
from infrastructure.firestore.client import FirestoreClient, FirestoreConflictError, FirestoreError
from infrastructure.firestore.competitions import documents
from support.api_case import ApiTestCase

SCRAPED = [{"nom": "BULAND", "prenom": "Julia", "licence": "930654", "classement": "9", "total_categorie": 20,
            "categorie": "U13Femme"}]


def competition_doc() -> Dict[str, Any]:  # Any: Firestore document fields
    return {"id": 123, "_doc_id": "123", "_update_time": "t1", "nom": "Test Comp", "participants": [
        {"nom": "BULAND", "prenom": "Julia", "num_licence": "930654"},
        {"nom": "DUPONT", "prenom": "Jean", "num_licence": "000000", "statut_paiement": "Payé"},
    ]}


def test_batch_report_coerces_scraped_details() -> None:
    report = BatchReport.model_validate({
        "status": "success",
        "executed_at": "2026-10-22T07:00:00",
        "competitions_checked": 3,
        "competitions_updated": 1,
        "email_sent": True,
        "notification_email": "club@example.org",
        "details": [
            {"id": 12, "nom": None, "date": 20261001, "lieu": None, "url": None, "athletes": None, "status": "found"},
            {"id": "c2", "athletes": [["Dupont", 3], "Martin"], "extra": "ignored"},
            {"id": "c3", "nom": "Open", "date": "2026-10-01", "lieu": "Lyon", "url": "https://x", "athletes": "<html>",
             "status": "pending"},
        ],
    })

    first, second, third = report.details
    assert (first.id, first.nom, first.date, first.lieu, first.url, first.athletes) == ("12", "", "20261001", "", "", [])
    assert (second.nom, second.status, second.athletes) == ("", "pending", [["Dupont", 3], "Martin"])
    assert third.athletes == []


class TestResultsSettingsRoute(ApiTestCase):

    def test_window_days_is_read_and_saved(self) -> None:
        self.assertEqual(self.client.get("/api/settings/competitions-results").json()["window_days"], 30)
        saved = self.client.post("/api/settings/competitions-results",
                                 json={"notification_email": "club@example.org", "window_days": 45}).json()
        self.assertEqual(saved["window_days"], 45)
        self.assertEqual(self.client.get("/api/settings/competitions-results").json()["window_days"], 45)
        # Without window_days: unchanged
        self.client.post("/api/settings/competitions-results", json={"notification_email": "club@example.org"})
        self.assertEqual(self.client.get("/api/settings/competitions-results").json()["window_days"], 45)

    def test_window_days_out_of_range_is_refused(self) -> None:
        for days in (0, 366):
            r = self.client.post("/api/settings/competitions-results",
                                 json={"notification_email": "club@example.org", "window_days": days})
            self.assertEqual(r.status_code, 400, days)
        self.assertEqual(self.client.get("/api/settings/competitions-results").json()["notification_email"],
                         DEFAULT_RESULTS_NOTIFICATION_EMAIL)  # checked before anything is saved

    def test_firestore_failure_answers_503(self) -> None:
        with patch("infrastructure.firestore.app_settings.AppSettingsRepository.save", side_effect=FirestoreError("down")):
            r = self.client.post("/api/settings/competitions-results", json={"notification_email": "club@example.org"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["status"], "error")


class TestFetchCompetitionResults(ApiTestCase):
    """POST /api/competitions/{id}/fetch-results: rankings written under the lock, every failure reported."""

    def fetch(self, body: Dict[str, Any], doc: Any = None, scraped: Any = SCRAPED, writes: Any = None):  # Any: doc or exception
        writes = [] if writes is None else writes
        def update_fields(collection: str, doc_id: str, fields: Dict[str, Any], expected_update_time: Any = None) -> None:
            if isinstance(self.write_error, Exception):
                raise self.write_error
            writes.append((doc_id, fields, expected_update_time))
        load = {"side_effect": doc} if isinstance(doc, Exception) else {"return_value": doc}
        scrape = {"side_effect": scraped} if isinstance(scraped, Exception) else {"return_value": scraped}
        with patch.object(documents, "load_comp_doc", **load), \
             patch("services.competitions.results_batch.fetch_and_parse_mycompet_results", **scrape), \
             patch("services.competitions.results_batch.find_mycompet_result_url", return_value="") as search, \
             patch.object(FirestoreClient, "update_fields", side_effect=update_fields):
            response = self.client.post("/api/competitions/123/fetch-results", json=body)
        self.search = search
        return response

    def setUp(self) -> None:
        super().setUp()
        self.write_error: Any = None

    def test_rankings_written_with_the_lock(self) -> None:
        writes: List[Any] = []
        r = self.fetch({"url": "13660", "club": "JONAGE"}, doc=competition_doc(), writes=writes)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["matched_count"], r.json()["total_scraped"]), (1, 1))
        [(doc_id, fields, expected)] = writes
        self.assertEqual((doc_id, expected), ("123", "t1"))
        julia, jean = fields["participants"]
        self.assertEqual(julia["classement"], "9")
        self.assertEqual(jean["statut_paiement"], "Payé")  # other fields untouched
        self.assertTrue(fields["url_resultats"].endswith("13660"))

    def test_url_kept_when_nobody_matches(self) -> None:
        writes: List[Any] = []
        r = self.fetch({"url": "13660"}, doc=competition_doc(), scraped=[{"nom": "X", "prenom": "Y", "licence": "1"}], writes=writes)
        self.assertEqual((r.status_code, r.json()["matched_count"]), (200, 0))
        [(_, fields, expected)] = writes
        self.assertNotIn("participants", fields)
        self.assertEqual(expected, "t1")

    def test_failed_write_is_an_error_not_a_success(self) -> None:
        for failure in (FirestoreError("HTTP 500"), FirestoreConflictError("lost every retry")):
            with self.subTest(failure=type(failure).__name__):
                self.write_error = failure
                with patch("time.sleep"):
                    r = self.fetch({"url": "13660"}, doc=competition_doc())
                self.assertEqual(r.status_code, 503)
                self.assertNotIn("HTTP 500", r.text)

    def test_failed_read_is_an_error(self) -> None:
        r = self.fetch({"url": "13660"}, doc=FirestoreError("HTTP 500"))
        self.assertEqual(r.status_code, 503)

    def test_unknown_competition(self) -> None:
        self.assertEqual(self.fetch({"url": "13660"}, doc=None).status_code, 404)

    def test_needs_url_when_no_page_is_found(self) -> None:
        r = self.fetch({}, doc=competition_doc())
        self.assertEqual((r.status_code, r.json()["code"]), (404, "needs_url"))
        self.search.assert_called_once()

    def test_mycompet_failure_is_upstream(self) -> None:
        r = self.fetch({"url": "13660"}, doc=competition_doc(), scraped=UpstreamUnavailable("HTTP 500 from mycompet"))
        self.assertEqual(r.status_code, 502)

    def test_untyped_body_refused(self) -> None:
        self.assertEqual(self.fetch({"url": "13660", "result_id": "1"}, doc=competition_doc()).status_code, 422)
        self.assertEqual(self.client.post("/api/competitions/not-a-number/fetch-results", json={}).status_code, 422)
