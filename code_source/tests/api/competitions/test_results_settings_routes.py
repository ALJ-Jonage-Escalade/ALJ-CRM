"""Results batch: the Cloud Scheduler cron route and the settings of the results e-mail."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestResultsSettingsRoutes(unittest.TestCase):
    def _temp_database(self, name):
        """SqliteDatabase on an empty database for the test."""
        from infrastructure.sqlite.connection import SqliteDatabase
        temp_dir = tempfile.mkdtemp()
        orig_db_path = SqliteDatabase.get_db_path()
        SqliteDatabase.set_db_path(os.path.join(temp_dir, name))
        SqliteDatabase.setup_database()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        self.addCleanup(SqliteDatabase.set_db_path, orig_db_path)

    def test_competitions_results_cron_and_settings_endpoints(self):
        """Vérifie les endpoints de configuration et de cron du batch des résultats MyCompet."""
        from support.fake_firestore import use_fake_firestore
        use_fake_firestore(self)
        from server import app
        client = TestClient(app)

        # 1. GET /api/settings/competitions-results
        res = client.get("/api/settings/competitions-results").json()
        self.assertEqual(res.get("status"), "success")
        self.assertIn("@", res["notification_email"])
        self.assertIn("cron_schedule", res)

        # 2. POST /api/settings/competitions-results
        up_res = client.post("/api/settings/competitions-results", json={"notification_email": "test.notif@alj-jonage.fr"}).json()
        self.assertEqual(up_res.get("status"), "success")
        self.assertEqual(up_res.get("notification_email"), "test.notif@alj-jonage.fr")
        bad = client.post("/api/settings/competitions-results", json={"notification_email": "pas-une-adresse"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json(), {"status": "error", "message": "Adresse e-mail de notification invalide."})

        # 2b. POST avec plusieurs e-mails
        multi_res = client.post("/api/settings/competitions-results", json={"notification_email": "coach1@alj-jonage.fr, coach2@alj-jonage.fr"}).json()
        self.assertEqual(multi_res.get("status"), "success")
        self.assertEqual(multi_res.get("notification_email"), "coach1@alj-jonage.fr, coach2@alj-jonage.fr")

        # Rétablir l'adresse par défaut
        client.post("/api/settings/competitions-results", json={"notification_email": "david.lopez@alj-jonage.fr"})

        # 3. POST /api/competitions/cron/fetch-results
        with patch("services.competitions.results_batch.CompetitionResultsBatchService.run_daily_batch") as mock_batch:
            mock_batch.return_value = {
                "status": "success",
                "executed_at": "2026-10-22T07:00:00",
                "competitions_checked": 1,
                "competitions_updated": 0,
                "email_sent": False,
                "notification_email": "david.lopez@alj-jonage.fr",
                "details": [{"id": "c1", "nom": "Open", "date": "2026-10-01", "lieu": "Lyon", "url": "", "athletes": [],
                             "status": "pending"}],
            }
            cron_resp = client.post("/api/competitions/cron/fetch-results?force=true")
            self.assertEqual(cron_resp.status_code, 200)
            self.assertEqual(cron_resp.json().get("status"), "success")
            mock_batch.assert_called_once()
