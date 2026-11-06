"""Member writes (admin): manual addition and record edits, persisted in the SQLite cache; season tariffs."""

import os
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from infrastructure.security.api_auth import Role
from server import app


class TestMemberWriteRoutes(unittest.TestCase):
    def _temp_database(self, name):
        """SqliteDatabase on an empty database for the test."""
        from infrastructure.sqlite.connection import SqliteDatabase
        temp_dir = tempfile.mkdtemp()
        orig_db_path = SqliteDatabase.get_db_path()
        SqliteDatabase.set_db_path(os.path.join(temp_dir, name))
        SqliteDatabase.setup_database()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        self.addCleanup(SqliteDatabase.set_db_path, orig_db_path)

    def test_member_add_requires_admin_role(self):
        """Les endpoints de création manuelle d'adhérents exigent le rôle admin."""
        from infrastructure.security.api_auth import required_role
        self.assertEqual(required_role("POST", "/api/members/create"), Role.ADMIN)
        self.assertEqual(required_role("POST", "/api/members/add"), Role.ADMIN)

    def test_member_add_endpoint_and_sqlite_persistence(self):
        """add_member_api persiste le nouvel adhérent, la commande et l'achat dans SQLite."""
        import shutil
        import tempfile

        from api.members.members import add_member_api
        from api.members.schemas import MemberCreate
        from infrastructure.sqlite.connection import SqliteDatabase

        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_member_add.db")
        orig_db_path = SqliteDatabase.get_db_path()
        try:
            SqliteDatabase.set_db_path(db_path)
            SqliteDatabase.setup_database()
            conn = SqliteDatabase.get_connection()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO seasons (id, name, is_active) VALUES (1, '2026-2027', 1)")
            conn.commit()
            conn.close()

            payload = {
                "season": "2026-2027",
                "fields": {
                    "last_name": "VALENTIN",
                    "first_name": "Claire",
                    "birth_date": "2010-05-14",
                    "sex": "F",
                    "tarif_name": "Cours Ados 1 (Lundi)",
                    "status": "Validé",
                    "amount": 195.0,
                    "licence_ffme": "654321",
                    "badge_rouge": "Oui",
                    "autonomie_bloc": "Oui",
                    "email_primary": "claire.valentin@example.com",
                    "email_secondary": "parents.valentin@example.com",
                    "phone": "06 11 22 33 44",
                    "address": "15 rue des Alpes",
                    "zip_code": "69330",
                    "city": "Jonage",
                    "commentaires_correctif": "Inscription manuelle web bureau"
                }
            }

            res = add_member_api(MemberCreate.model_validate(payload))
            self.assertEqual(res.status, "success")
            self.assertTrue(res.order_ref.startswith("MANUEL-"))

            # Vérification dans SQLite
            conn = SqliteDatabase.get_connection()
            u = conn.execute("SELECT * FROM users WHERE last_name = 'VALENTIN'").fetchone()
            self.assertIsNotNone(u)
            self.assertEqual(u["first_name"], "Claire")
            self.assertEqual(u["birth_date"], "2010-05-14")
            self.assertEqual(u["sex"], "F")
            self.assertEqual(u["licence_ffme"], "654321")
            self.assertEqual(u["badge_rouge"], "Oui")
            self.assertEqual(u["autonomie_bloc"], "Oui")
            self.assertEqual(u["email_primary"], "claire.valentin@example.com")
            self.assertEqual(u["email_secondary"], "parents.valentin@example.com")
            self.assertEqual(u["phone"], "06 11 22 33 44")
            self.assertEqual(u["address"], "15 rue des Alpes")
            self.assertEqual(u["zip_code"], "69330")
            self.assertEqual(u["city"], "Jonage")

            p = conn.execute("SELECT * FROM purchases WHERE user_id = ?", (u["id"],)).fetchone()
            self.assertIsNotNone(p)
            self.assertEqual(p["tarif_name"], "Cours Ados 1 (Lundi)")
            self.assertEqual(float(p["amount"]), 195.0)
            self.assertEqual(p["status_normalized"], "Validé")
            self.assertEqual(p["commentaires_correctif"], "Inscription manuelle web bureau")

            o = conn.execute("SELECT * FROM orders WHERE id = ?", (p["order_id"],)).fetchone()
            self.assertIsNotNone(o)
            self.assertEqual(o["order_ref"], res.order_ref)
            self.assertEqual(o["payer_email"], "claire.valentin@example.com")
            conn.close()
        finally:
            SqliteDatabase.set_db_path(orig_db_path)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_member_add_validation(self):
        """MemberService.add_member rejette les requêtes avec champs obligatoires manquants (400 côté API)."""
        from domain.errors import InvalidRequest
        from services.members.members import MemberService

        for fields in ({"first_name": "Jean", "birth_date": "2000-01-01", "tarif_name": "Licence"},  # nom manquant
                       {"last_name": "DUPONT", "first_name": "Jean", "tarif_name": "Licence"},  # date de naissance manquante
                       {"last_name": "DUPONT", "first_name": "Jean", "birth_date": "2000-01-01"}):  # tarif manquant
            with self.subTest(fields=fields), self.assertRaises(InvalidRequest):
                MemberService.add_member(fields)

    def test_member_update_requires_admin_role(self):
        """L'endpoint /api/members/update exige le rôle admin."""
        from infrastructure.security.api_auth import required_role
        self.assertEqual(required_role("POST", "/api/members/update"), Role.ADMIN)

    def test_member_update_endpoint_and_sqlite_persistence(self):
        """update_member_api persiste les badges, emails, téléphone et créneau dans SQLite."""
        import shutil
        import tempfile

        from api.members.members import update_member_api
        from api.members.schemas import MemberUpdate
        from infrastructure.sqlite.connection import SqliteDatabase

        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_member_edit.db")
        orig_db_path = SqliteDatabase.get_db_path()
        try:
            SqliteDatabase.set_db_path(db_path)
            SqliteDatabase.setup_database()
            conn = SqliteDatabase.get_connection()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO seasons (id, name, is_active) VALUES (1, '2026-2027', 1)")
            c.execute("""
                INSERT INTO users (id, last_name, first_name, last_name_key, first_name_key, email_primary, email_secondary, phone, badge_rouge, autonomie_bloc)
                VALUES (50, 'BERNARD', 'Luc', 'bernard', 'luc', 'luc@old.fr', '', '0600000000', 'Non', 'Non')
            """)
            c.execute("""
                INSERT INTO orders (id, season_id, order_ref)
                VALUES (60, 1, 'CMD-BERNARD-1')
            """)
            c.execute("""
                INSERT INTO purchases (id, order_id, user_id, tarif_name, amount, status)
                VALUES (70, 60, 50, 'Séance autonome', 130.0, 'Payé')
            """)
            conn.commit()
            conn.close()

            payload = {
                "user_id": 50,
                "purchase_id": 70,
                "order_ref": "CMD-BERNARD-1",
                "fields": {
                    "licence_ffme": "778899",
                    "address": "12 chemin du Moulin",
                    "zip_code": "69330",
                    "city": "Jonage",
                    "badge_rouge": "Oui",
                    "autonomie_bloc": "Oui",
                    "email_primary": "luc.bernard@nouveau.fr",
                    "email_secondary": "parent.luc@example.com",
                    "phone": "06 99 88 77 66",
                    "tarif_name": "Cours Ados 1 (Lundi)",
                    "status": "Annulé",
                    "commentaires_correctif": "Certificat médical papier fourni en main propre le 14/10."
                }
            }

            res = update_member_api(MemberUpdate.model_validate(payload))
            self.assertEqual(res.status, "success")

            # Vérification dans la table users
            conn = SqliteDatabase.get_connection()
            u = conn.execute("SELECT * FROM users WHERE id = 50").fetchone()
            self.assertEqual(u["licence_ffme"], "778899")
            self.assertEqual(u["address"], "12 chemin du Moulin")
            self.assertEqual(u["zip_code"], "69330")
            self.assertEqual(u["city"], "Jonage")
            self.assertEqual(u["badge_rouge"], "Oui")
            self.assertEqual(u["autonomie_bloc"], "Oui")
            self.assertEqual(u["email_primary"], "luc.bernard@nouveau.fr")
            self.assertEqual(u["email_secondary"], "parent.luc@example.com")
            self.assertEqual(u["phone"], "06 99 88 77 66")

            # Vérification dans la table purchases (créneau & statut & commentaire)
            p = conn.execute("SELECT * FROM purchases WHERE id = 70").fetchone()
            self.assertEqual(p["tarif_name"], "Cours Ados 1 (Lundi)")
            self.assertEqual(p["status"], "Annulé")
            self.assertEqual(p["status_normalized"], "Annulé")
            self.assertEqual(p["commentaires_correctif"], "Certificat médical papier fourni en main propre le 14/10.")
            self.assertEqual(p["is_modified"], "Oui")

            # Vérification dans la table orders (statut de commande)
            o = conn.execute("SELECT * FROM orders WHERE id = 60").fetchone()
            self.assertEqual(o["status"], "Annulé")
            self.assertEqual(o["status_normalized"], "Annulé")
            conn.close()
        finally:
            SqliteDatabase.set_db_path(orig_db_path)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_season_tarifs_endpoint(self):
        """GET /api/season-tarifs retourne les tarifs disponibles de la saison active."""
        res = TestClient(app).get("/api/season-tarifs", params={"season": "2026-2027"}).json()
        self.assertEqual((res["status"], res["season"]), ("success", "2026-2027"))
        self.assertIn("Licence sèche", res["tarifs"])
