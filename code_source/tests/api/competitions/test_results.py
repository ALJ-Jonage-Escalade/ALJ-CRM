"""Schemas of src/api/competitions/results.py: the batch report accepts whatever the scraped data holds."""

from __future__ import annotations

from api.competitions.schemas.results import BatchReport
from support.api_case import ApiTestCase


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
        self.assertEqual((saved["window_days"], saved["saved"]), (45, True))
        self.assertEqual(self.client.get("/api/settings/competitions-results").json()["window_days"], 45)
        # Without window_days: unchanged
        self.client.post("/api/settings/competitions-results", json={"notification_email": "club@example.org"})
        self.assertEqual(self.client.get("/api/settings/competitions-results").json()["window_days"], 45)

    def test_window_days_out_of_range_is_refused(self) -> None:
        for days in (0, 366):
            r = self.client.post("/api/settings/competitions-results",
                                 json={"notification_email": "club@example.org", "window_days": days})
            self.assertEqual(r.status_code, 400, days)
