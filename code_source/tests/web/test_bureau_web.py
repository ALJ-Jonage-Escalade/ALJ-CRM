"""The pages of the Vue app and their former addresses, served without data; the API stays protected.

The API routes the pages call are tested next to their routers, in tests/api/."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

_code_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from api.web.pages import get_bureau_home, get_bureau_page, get_bureau_sub_page
from infrastructure.security import api_auth
from infrastructure.security.api_auth import Role
from server import app

WEB = os.path.join(_code_root, "web")


class TestBureauFiles(unittest.TestCase):

    def test_no_former_page_left(self):
        """Every page is the Vue application's: no HTML page nor script left in web/ (plan phase 12)."""
        self.assertEqual([n for _, _, files in os.walk(WEB) for n in files if n.endswith((".html", ".js", ".css"))], [])

    def test_routes_serve_only_known_pages(self):
        self.assertEqual(get_bureau_page("index.html").status_code, 404)
        self.assertEqual(get_bureau_page("..%2Fserver.py").status_code, 404)
        self.assertEqual(get_bureau_page("inconnue").status_code, 404)
        self.assertEqual(get_bureau_sub_page("competitions", "inconnue").status_code, 404)
        self.assertEqual(get_bureau_sub_page("planning", "bilan").status_code, 404)
        self.assertEqual(get_bureau_sub_page("inconnue", "bilan").status_code, 404)
        self.assertEqual(get_bureau_sub_page("outils", "bilan").status_code, 404)
        self.assertEqual(get_bureau_sub_page("parametres", "bilan").status_code, 404)

    def _temp_database(self, name):
        """SqliteDatabase on an empty database for the test."""
        from infrastructure.sqlite.connection import SqliteDatabase
        temp_dir = tempfile.mkdtemp()
        orig_db_path = SqliteDatabase.get_db_path()
        SqliteDatabase.set_db_path(os.path.join(temp_dir, name))
        SqliteDatabase.setup_database()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        self.addCleanup(SqliteDatabase.set_db_path, orig_db_path)

class TestBureauAccess(unittest.TestCase):
    """Le portail reste public (pages) tandis que l'API reste protégée."""

    def setUp(self):
        self.env = patch.dict(os.environ, {"ALJ_API_AUTH": "required"})
        self.env.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop()

    def test_portal_public_api_protected(self):
        for path in ("/bureau", "/bureau/", "/bureau/adherents", "/bureau/administration", "/bureau/communications", "/bureau/competitions",
                     "/bureau/planning", "/bureau/outils", "/bureau/parametres", "/bureau/competitions/helloasso",
                     "/bureau/competitions/bilan", "/bureau/competitions/coachs", "/competitions/helloasso",
                     "/competitions/bilan", "/competitions/coachs", "/bureau/outils/pivot", "/bureau/outils/stats",
                     "/bureau/outils/presence", "/bureau/outils/ffme", "/bureau/outils/ffme-import",
                     "/bureau/outils/helloasso-import", "/bureau/parametres/campagnes", "/bureau/planning/tableau"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/bureau/inconnue").status_code, 404)
        self.assertEqual(self.client.get("/bureau/competitions/inconnue").status_code, 404)
        self.assertEqual(self.client.get("/api/email-status").status_code, 401)

    def test_portal_content_types(self):
        self.assertIn("text/html", self.client.get("/bureau/").headers["content-type"])
        self.assertIn("text/html", self.client.get("/bureau/planning").headers["content-type"])
        # Former shared scripts: gone, and the address is no longer public (401 before the 404)
        self.assertEqual(self.client.get("/static-web/alj-core.js").status_code, 401)

    def test_required_role_for_portal(self):
        r = api_auth.required_role
        for path in ("/bureau", "/bureau/", "/bureau/adherents", "/bureau/administration", "/bureau/communications", "/bureau/competitions", "/bureau/planning", "/bureau/outils", "/bureau/parametres"):
            self.assertIsNone(r("GET", path), path)
        self.assertEqual(r("GET", "/api/email-status"), Role.COACH)


class TestVueApp(unittest.TestCase):
    """Pages migrated to the Vue application (frontend/): its entry page and assets (api/web/pages.py)."""

    def setUp(self):
        self.dist = tempfile.mkdtemp(prefix="alj-dist-")
        self.env = patch.dict(os.environ, {"ALJ_FRONTEND_DIST": self.dist})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dist, ignore_errors=True)

    def test_accueil_without_build_explains_how_to_build(self):
        r = get_bureau_home()
        self.assertEqual(r.status_code, 503)
        self.assertIn(b"npm run build", r.body)

    def test_accueil_serves_the_entry_page_uncached(self):
        with open(os.path.join(self.dist, "index.html"), "w", encoding="utf-8") as f:
            f.write("<div id=\"app\"></div>")
        r = TestClient(app).get("/bureau/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, '<div id="app"></div>')
        self.assertEqual(r.headers["cache-control"], "no-cache")
        self.assertEqual(TestClient(app).get("/bureau").status_code, 200)

    def test_assets_served_under_spa(self):
        """The mount reads the folder of the build at startup: the app's own one (frontend/dist), maybe not built."""
        r = TestClient(app).get("/spa/assets/does-not-exist.js")
        self.assertEqual(r.status_code, 404)  # not a server error when the frontend is not built

    def test_migrated_pages_serve_the_entry_page(self):
        with open(os.path.join(self.dist, "index.html"), "w", encoding="utf-8") as f:
            f.write("<div id=\"app\"></div>")
        for page in ("adherents", "communications", "competitions", "outils", "parametres", "planning"):
            r = TestClient(app).get(f"/bureau/{page}")
            self.assertEqual(r.status_code, 200, page)
            self.assertEqual(r.text, '<div id="app"></div>', page)
        # The competitions and the Google sign-in callback, on phones as on desktop (?vue=: former links)
        for path in ("/competitions", "/competitions?vue=mobile", "/competitions?login=1"):
            self.assertEqual(TestClient(app).get(path).text, '<div id="app"></div>', path)
        r = TestClient(app).get("/", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (302, "/competitions"))
        # The directory, on phones as on desktop (?vue=pwa: link of the competitions page)
        for path in ("/index", "/index?vue=pwa"):
            self.assertEqual(TestClient(app).get(path).text, '<div id="app"></div>', path)
        self.assertFalse(os.path.exists(os.path.join(WEB, "index.html")))

    def test_former_page_files_redirect(self):
        """The former pages of web/ (served by the /annuaire mount): their screen, query kept (?vue=… included)."""
        for path, target in (("/annuaire/", "/index"), ("/annuaire/index.html?vue=pwa", "/index?vue=pwa"),
                             ("/annuaire/competitions.html", "/competitions"),
                             ("/annuaire/competitions.html?vue=mobile", "/competitions?vue=mobile"),
                             ("/annuaire/bureau/", "/bureau/"), ("/annuaire/bureau/index.html", "/bureau/"),
                             ("/annuaire/bureau/adherents.html?id=3", "/bureau/adherents?id=3"),
                             ("/annuaire/bureau/competitions.html", "/bureau/competitions")):
            r = TestClient(app).get(path, follow_redirects=False)
            self.assertEqual((r.status_code, r.headers.get("location")), (302, target), path)
        self.assertEqual(TestClient(app).get("/annuaire/bureau/inconnue.html").status_code, 404)
        self.assertEqual(TestClient(app).get("/annuaire/assets/logo.png").status_code, 200)  # the mount still serves the logo

    def test_former_management_pages_redirect(self):
        """The former competitions management pages (phone and office): the competitions screen, query kept."""
        for path, target in (("/competitions/gestion", "/competitions"), ("/bureau/competitions-gestion?id=12", "/bureau/competitions?id=12")):
            r = TestClient(app).get(path, follow_redirects=False)
            self.assertEqual((r.status_code, r.headers["location"]), (302, target), path)
        self.assertEqual(get_bureau_page("competitions-gestion").status_code, 404)  # not a page of its own any more

    def test_former_record_url_goes_to_the_list(self):
        """/bureau/adherents-fiche (member record of the former page, 2.14) opens the record in the Vue app."""
        r = TestClient(app).get("/bureau/adherents-fiche?id=12&saison=2026-2027", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/bureau/adherents?id=12&saison=2026-2027")


class TestRuntimeConfig(unittest.TestCase):
    """Runtime configuration served by the server (/runtime-config.js): the basis of the emulator dev mode."""

    def test_runtime_config_is_public(self):
        self.assertIsNone(api_auth.required_role("GET", "/runtime-config.js"))

if __name__ == "__main__":
    unittest.main()
