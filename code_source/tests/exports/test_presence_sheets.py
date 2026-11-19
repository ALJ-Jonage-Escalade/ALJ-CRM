import unittest
import os
import shutil
import sys
import tempfile

# Ajustement du chemin pour importer les modules depuis 'src'
_test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(os.path.dirname(_test_dir), "src") if os.path.basename(_test_dir) == "tests" else _test_dir
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.members import MemberRepository
from infrastructure.sqlite.planning import PlanningRepository
from exports.presence_sheets import clean_filename


def _member(order_ref, last, first, tarif):
    """HelloAsso item in the pipeline's canonical format (legacy keys)."""
    return {
        "order_ref": order_ref,
        "order_date": "2026-08-20T10:00:00",
        "status": "Validated",
        "tarif_name": tarif,
        "amount": 150.0,
        "user_lastName": last,
        "user_firstName": first,
        "champ_Date de naissance de l'adhérent": "1990-05-15",
    }


class TestPresenceSheetGenerator(unittest.TestCase):

    def setUp(self):
        # The export endpoints read the database: use a seeded temporary one, never data/database.db.
        self._original_db_path = SqliteDatabase.get_db_path()
        self._tmpdir = tempfile.mkdtemp(prefix="alj_presence_test_")
        SqliteDatabase.set_db_path(os.path.join(self._tmpdir, "database.db"))
        SqliteDatabase.setup_database()
        PlanningRepository.save_planning_item({"groupe": "Adultes autonomes", "type": "autonome", "jour": "Mardi",
                                             "horaires": "19h-22h", "helloasso_tarifs": ["Adultes autonomes"],
                                             "seance_autonome": True})
        PlanningRepository.save_planning_item({"groupe": "Loisir cours", "jour": "Lundi", "horaires": "18h-20h",
                                             "encadrants": ["Camille DIDIER"], "helloasso_tarifs": ["Loisir cours"]})
        MemberRepository.upsert_members([
            _member("ORD-1", "MARTIN", "Leo", "Adultes autonomes"),
            _member("ORD-2", "DURAND", "Lea", "Loisir cours"),
        ], "2026-2027")

    def tearDown(self):
        SqliteDatabase.set_db_path(self._original_db_path)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_clean_filename(self):
        """Vérifie le nettoyage des noms de fichiers de présence."""
        self.assertEqual(clean_filename("Adultes autonomes"), "Adultes_autonomes")
        self.assertEqual(clean_filename("Loisir lycée / jeunes"), "Loisir_lycée_jeunes")
        self.assertEqual(clean_filename("Compétition - U15-U19"), "Compétition_-_U15-U19")

    def test_presence_api_config(self):
        """Vérifie que /api/presence/config renvoie la structure attendue pour l'IHM."""
        from fastapi.testclient import TestClient
        from server import app
        client = TestClient(app, base_url="http://localhost")
        resp = client.get("/api/presence/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("autonome", data)
        self.assertIn("cours", data)
        self.assertIn("default_dates", data)

    def test_presence_api_config_adds_the_ticked_course_groups_to_the_autonomous_sheet(self):
        """A course ticked « Séance autonome » keeps its course sheet; its members count on the autonomous sheet."""
        from fastapi.testclient import TestClient
        from server import app
        client = TestClient(app, base_url="http://localhost")
        saved = client.post("/api/planning/item", json={"groupe": "Perfectionnement U19 Adulte", "type": "perfectionnement",
                                                        "jour": "Mercredi", "horaires": "20h-22h",
                                                        "helloasso_tarifs": ["Perf adultes"], "seance_autonome": True})
        self.assertTrue(saved.json()["item"]["seance_autonome"])
        MemberRepository.upsert_members([_member("ORD-4", "ROBERT", "Ana", "Perf adultes")], "2026-2027")

        autonome = client.get("/api/presence/config").json()["autonome"]
        cours = [c["groupe"] for c in client.get("/api/presence/config").json()["cours"]]
        self.assertEqual((autonome["groups"], autonome["extra_groups"]), (["Adultes autonomes"], ["Perfectionnement U19 Adulte"]))
        self.assertEqual(autonome["total"], 2)
        self.assertEqual(cours, ["Loisir cours", "Perfectionnement U19 Adulte"])

    def test_presence_api_export_autonome(self):
        """Vérifie que /api/presence/export génère et télécharge une feuille Excel pour les autonomes."""
        from fastapi.testclient import TestClient
        from server import app
        client = TestClient(app, base_url="http://localhost")
        resp = client.post("/api/presence/export", json={"variant": "autonome", "show_health_col": True})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("attachment", resp.headers.get("content-disposition", ""))
        self.assertGreater(len(resp.content), 1000)

    def test_presence_api_export_cours(self):
        """Vérifie que /api/presence/export génère et télécharge les feuilles des cours (same_sheet=True)."""
        from fastapi.testclient import TestClient
        from server import app
        client = TestClient(app, base_url="http://localhost")
        resp = client.post("/api/presence/export", json={"variant": "cours", "same_sheet": True})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("attachment", resp.headers.get("content-disposition", ""))
        self.assertGreater(len(resp.content), 1000)

    def test_presence_api_export_readonly_root_dir(self):
        """Cloud Run : ROOT_DIR (« / ») n'est pas accessible en écriture ; le QRCode WhatsApp
        du créneau est alors généré localement dans le dossier temporaire, sans appel réseau."""
        import io
        import zipfile
        from unittest import mock

        from fastapi.testclient import TestClient
        from server import app
        PlanningRepository.save_planning_item({"groupe": "Loisir WhatsApp", "jour": "Jeudi", "horaires": "18h-20h",
                                             "helloasso_tarifs": ["Loisir WhatsApp"],
                                             "whatsapp_link": "https://chat.whatsapp.com/exemple"})
        MemberRepository.upsert_members([_member("ORD-3", "PETIT", "Noe", "Loisir WhatsApp")], "2026-2027")
        # A regular file as ROOT_DIR makes os.makedirs fail on every OS
        # (chmod 0o555 does not prevent creating subfolders on Windows).
        unwritable_root = os.path.join(self._tmpdir, "not_a_dir")
        with open(unwritable_root, "w", encoding="utf-8"):
            pass
        client = TestClient(app, base_url="http://localhost")
        with mock.patch("paths.ROOT_DIR", unwritable_root), \
                mock.patch("tempfile.tempdir", self._tmpdir), \
                mock.patch("requests.get") as http_get:
            resp = client.post("/api/presence/export", json={"variant": "cours", "selected_groups": ["Loisir WhatsApp"]})
        self.assertEqual(resp.status_code, 200, resp.text)
        http_get.assert_not_called()
        self.assertTrue(os.path.isfile(unwritable_root))
        self.assertTrue(os.path.isfile(os.path.join(self._tmpdir, "alj_qrcodes", "QRCode_WhatsApp_Loisir WhatsApp.png")))
        with zipfile.ZipFile(io.BytesIO(resp.content)) as xlsx:
            self.assertTrue(any(name.startswith("xl/media/") for name in xlsx.namelist()))
