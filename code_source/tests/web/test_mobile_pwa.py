"""
PWA shell (manifest, service worker built with the Vue application, app version); the screens are the Vue
application's (frontend/).
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

_tests_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_code_root = os.path.dirname(_tests_dir)
_src_dir = os.path.join(_code_root, "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from fastapi.testclient import TestClient

from api.web.pwa import get_manifest, get_web_version
from domain.constants import APP_VERSION
from server import app


class TestMobilePWA(unittest.TestCase):
    """Vérifie la conformité PWA et les fonctionnalités de l'interface mobile."""

    def test_manifest_endpoint(self):
        resp = get_manifest()
        self.assertEqual(resp.media_type, "application/manifest+json")
        self.assertTrue(os.path.exists(resp.path))
        with open(resp.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "ALJ Escalade — Compétitions")
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["theme_color"], "#1E293B")
        self.assertEqual(TestClient(app).get(data["icons"][0]["src"]).status_code, 200)

    def test_web_version_is_the_app_version(self):
        """One version only (VERSION, APP_VERSION): no separate web version any more."""
        self.assertEqual(get_web_version().model_dump(), {"app_version": APP_VERSION})

    def test_no_hand_written_service_worker(self):
        """The service worker comes from the build (frontend/src/sw.ts): no hand-kept precache list in web/."""
        self.assertEqual(sorted(os.listdir(os.path.join(_code_root, "web"))), ["assets", "manifest.webmanifest"])


class TestBuiltServiceWorker(unittest.TestCase):
    """/sw.js answers the worker of the build (frontend/dist/sw.js), checked again on every visit."""

    def setUp(self):
        self.dist = tempfile.mkdtemp(prefix="alj-dist-")
        self.env = patch.dict(os.environ, {"ALJ_FRONTEND_DIST": self.dist})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dist, ignore_errors=True)

    def test_without_build_not_found(self):
        self.assertEqual(TestClient(app).get("/sw.js").status_code, 404)

    def test_serves_the_built_worker_uncached(self):
        with open(os.path.join(self.dist, "sw.js"), "w", encoding="utf-8") as f:
            f.write("self.skipWaiting();")
        r = TestClient(app).get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, "self.skipWaiting();")
        self.assertIn("javascript", r.headers["content-type"])
        self.assertEqual(r.headers["cache-control"], "no-cache")


if __name__ == "__main__":
    unittest.main()
