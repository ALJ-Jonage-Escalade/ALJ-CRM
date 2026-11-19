"""Planning slots: create, edit, delete (coach), the Excel exports and the refusals."""

import os
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from server import app


class TestPlanningRoutes(unittest.TestCase):
    def _temp_database(self, name):
        """SqliteDatabase on an empty database for the test."""
        from infrastructure.sqlite.connection import SqliteDatabase
        temp_dir = tempfile.mkdtemp()
        orig_db_path = SqliteDatabase.get_db_path()
        SqliteDatabase.set_db_path(os.path.join(temp_dir, name))
        SqliteDatabase.setup_database()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        self.addCleanup(SqliteDatabase.set_db_path, orig_db_path)

    def test_planning_item_crud_and_export(self):
        """Vérifie la création, modification, suppression et export Excel des créneaux de planning."""
        self._temp_database("test_planning.db")
        client = TestClient(app)

        # 1. Création d'un nouveau créneau (champs absents : vides)
        new_slot = {
            "id": 0,
            "groupe": "Test Nouveau Créneau Web",
            "jour": "Mardi",
            "horaires": "19:00 - 20:30",
            "type": "cours",
            "categorie_age": "Adultes",
            "encadrants": ["Test Coach", " "],
            "helloasso_tarifs": ["Licence sèche"]
        }
        res_create = client.post("/api/planning/item", json=new_slot).json()
        self.assertEqual(res_create["status"], "success")
        saved_id = res_create["item"]["id"]
        self.assertGreater(saved_id, 0)
        expected = {**new_slot, "id": saved_id, "encadrants": ["Test Coach"], "whatsapp_link": "", "naissance_min": "", "naissance_max": "",
                    "seance_autonome": False}
        self.assertEqual(res_create["item"], expected)

        # 2. Modification du créneau
        updated = {**expected, "groupe": "Test Créneau Modifié Web", "seance_autonome": True}
        res_update = client.post("/api/planning/item", json=updated)
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(client.get("/api/planning").json(), [updated])

        # 3. Export Excel (grille et liste)
        for mode in ("grid", "list"):
            resp = client.get("/api/planning/export", params={"mode": mode, "season": "2026-2027"})
            self.assertEqual(resp.headers.get("content-type"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.assertIn("attachment", resp.headers.get("content-disposition", ""))
            self.assertGreater(len(resp.content), 1000)
        self.assertEqual(client.get("/api/planning/export", params={"mode": "autre"}).status_code, 422)

        # 4. Suppression
        self.assertEqual(client.delete(f"/api/planning/item/{saved_id}").json()["status"], "success")
        self.assertEqual(client.get("/api/planning").json(), [])
        r = client.delete(f"/api/planning/item/{saved_id}")
        self.assertEqual((r.status_code, r.json()["message"]), (404, f"Créneau #{saved_id} introuvable."))

    def test_planning_refusals(self):
        """Un créneau sans nom ou sans horaires est refusé ; une grille sans créneau placable aussi."""
        self._temp_database("test_planning_refusals.db")
        client = TestClient(app)
        for body, message in (
            ({"groupe": " ", "horaires": "18:00 - 20:00"}, "Le nom du groupe est obligatoire."),
            ({"groupe": "Loisir", "horaires": ""}, "Les horaires sont obligatoires."),
        ):
            with self.subTest(body=body):
                r = client.post("/api/planning/item", json=body)
                self.assertEqual((r.status_code, r.json()["message"]), (400, message))
        self.assertEqual(client.post("/api/planning/item", json={"groupe": "X", "horaires": "1", "inconnu": 1}).status_code, 422)
        self.assertEqual(client.get("/api/planning").json(), [])

        client.post("/api/planning/item", json={"groupe": "Autonome", "jour": "Lundi / Jeudi", "horaires": "20:00 - 22:00"})
        r = client.get("/api/planning/export", params={"mode": "grid", "season": "2026-2027"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Aucun créneau à placer sur la grille", r.json()["message"])
        self.assertEqual(client.get("/api/planning/export", params={"mode": "list", "season": "2026-2027"}).status_code, 200)
