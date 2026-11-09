"""Cloud cache routes: status (coach) and full sync (admin)."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from infrastructure.security.api_auth import Role


class TestCloudDbRoutes(unittest.TestCase):
    def _temp_database(self, name):
        """SqliteDatabase on an empty database for the test."""
        from infrastructure.sqlite.connection import SqliteDatabase
        temp_dir = tempfile.mkdtemp()
        orig_db_path = SqliteDatabase.get_db_path()
        SqliteDatabase.set_db_path(os.path.join(temp_dir, name))
        SqliteDatabase.setup_database()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        self.addCleanup(SqliteDatabase.set_db_path, orig_db_path)

    def test_cloud_db_status_endpoint(self):
        """Vérifie l'endpoint GET /api/cloud-db/status."""
        from server import app
        res = TestClient(app).get("/api/cloud-db/status").json()
        self.assertEqual(res.get("status"), "success")
        self.assertIn("db_exists", res)
        self.assertIn("pending", res)

    def test_sync_cloud_db_endpoint(self):
        """Vérifie l'endpoint POST /api/cloud-db/sync."""
        from api.integrations.cloud_db import sync_cloud_db_api
        with patch("infrastructure.firestore.cloud_database.CloudDatabase.is_enabled", return_value=True):
            with patch("infrastructure.firestore.cloud_database.CloudDatabase.sync", return_value={"status": "ok", "errors": []}):
                res = sync_cloud_db_api(force=True)
                self.assertEqual(res.status, "success")
                self.assertEqual(res.result.model_dump(), {"pulled": 0, "pushed": 0, "full": False})

    def test_sync_cloud_db_requires_admin_role(self):
        """POST /api/cloud-db/sync exige le rôle admin ; l'état du cache reste lisible par les coachs."""
        from infrastructure.security.api_auth import required_role
        self.assertEqual(required_role("POST", "/api/cloud-db/sync"), Role.ADMIN)
        self.assertEqual(required_role("GET", "/api/cloud-db/status"), Role.COACH)
