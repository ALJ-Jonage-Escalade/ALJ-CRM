"""
PWA shell of the competitions (manifest, service worker); the screens are the Vue application's (frontend/).
"""

import os
import sys
import unittest
import json

_tests_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(os.path.dirname(_tests_dir), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


from api.web.pwa import get_manifest, get_sw, get_web_version


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

    def test_service_worker_endpoint(self):
        resp = get_sw()
        self.assertEqual(resp.media_type, "application/javascript")
        self.assertTrue(os.path.exists(resp.path))
        with open(resp.path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertRegex(content, r'CACHE_NAME = "alj-escalade-v\d+"')
        self.assertIn("addEventListener(\"fetch\"", content)

    def test_web_version_is_the_service_worker_cache(self):
        """/api/web-version answers the number of the service worker's cache (until the build's worker, phase 12)."""
        version = get_web_version()["web_version"]
        self.assertRegex(version, r"^\d+$")
        with open(get_sw().path, "r", encoding="utf-8") as f:
            sw = f.read()
        self.assertIn(f'CACHE_NAME = "alj-escalade-v{version}"', sw)

    def test_offline_store(self):
        """Phase 5: the former pages' offline store (alj-store.js, the only script opening IndexedDB); the Vue app's
        port (frontend/src/lib/store.ts) and what it keeps are tested by Vitest and e2e/test_competitions_view.py."""
        web_dir = os.path.join(os.path.dirname(_tests_dir), "web")
        for root, _, files in os.walk(web_dir):
            for name in files:
                if not name.endswith((".html", ".js")):
                    continue
                path = os.path.join(root, name)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if name != "alj-store.js":
                    # alj-firebase.js deletes the old Firestore SDK copy (firestore/*) only
                    self.assertNotIn("indexedDB.open(", content, path)
                    self.assertNotIn("alj_snapshot:", content, path)  # old localStorage snapshots
        with open(get_sw().path, "r", encoding="utf-8") as f:
            self.assertIn('"/static-web/alj-store.js"', f.read())
        with open(os.path.join(web_dir, "shared", "alj-store.js"), "r", encoding="utf-8") as f:
            store = f.read()
        self.assertIn("const MAX_AGE_DAYS = 30;", store)
        self.assertIn("navigator.storage.persist()", store)
        self.assertIn('await run("outbox", "readwrite", s => s.clear());', store)  # clearAll empties the outbox


if __name__ == "__main__":
    unittest.main()
