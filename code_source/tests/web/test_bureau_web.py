"""
Tests du portail « bureau » :
- routes publiques (pages de l'application Vue, anciennes adresses) sans données ;
- endpoints de l'API appelés par les pages.
"""

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

from infrastructure.security import api_auth
from infrastructure.security.api_auth import Role
from api.web.pages import get_bureau_home, get_bureau_page, get_bureau_sub_page
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

    def test_cloud_db_status_endpoint(self):
        """Vérifie l'endpoint GET /api/cloud-db/status."""
        from server import app
        res = TestClient(app).get("/api/cloud-db/status").json()
        self.assertEqual(res.get("status"), "success")
        self.assertIn("db_exists", res)
        self.assertIn("pending", res)

    def test_build_attestation_pure_function_rules(self):
        """build_attestation respecte les règles de montant, d'annulation, de signature et de payeur."""
        from exports.attestation import build_attestation, get_safe_pdf_filename
        club = "club@alj.example"

        # 1. Validation montant manquant ou nul
        with self.assertRaises(ValueError):
            build_attestation({"first_name": "Jean", "last_name": "Dupont", "amount": 0}, club_email=club)
        with self.assertRaises(ValueError):
            build_attestation({"first_name": "Jean", "last_name": "Dupont", "amount": -10}, club_email=club)

        # 2. Validation commande annulée
        with self.assertRaises(ValueError):
            build_attestation({"first_name": "Jean", "last_name": "Dupont", "amount": 150, "status": "Annulé"}, club_email=club)
        with self.assertRaises(ValueError):
            build_attestation({"first_name": "Jean", "last_name": "Dupont", "amount": 150, "status": "Refunded"}, club_email=club)

        # 3. Payeur par défaut = adhérent
        m = {"first_name": "alex", "last_name": "martin", "amount": 195, "season_name": "2026-2027"}
        html = build_attestation(m, season="2026-2027", date_jour="14 juillet 2026", club_email=club)
        self.assertIn("MARTIN", html)
        self.assertIn("Alex", html)
        self.assertIn("195,00", html)
        self.assertIn("14 juillet 2026", html)
        self.assertIn("2026-2027", html)

        # 4. Signature & tampon garantis en base64 dans le HTML
        self.assertIn("data:image/jpeg;base64,", html)

        # 6. Nom de fichier sécurisé
        fn = get_safe_pdf_filename(m["last_name"], m["first_name"], "CMD-99")
        self.assertEqual(fn, "Attestation_MARTIN_Alex_CMD-99.pdf")

    def test_attestation_endpoints_require_admin_role(self):
        """Les endpoints /api/attestations exigent le rôle admin."""
        from infrastructure.security.api_auth import required_role
        self.assertEqual(required_role("POST", "/api/attestations/preview"), Role.ADMIN)
        self.assertEqual(required_role("POST", "/api/attestations/send"), Role.ADMIN)

    def test_send_attestation_records_email_sent_date(self):
        """send_attestation_api enregistre la date d'envoi dans SQLite et utilise le modèle par défaut."""
        import tempfile
        import shutil
        from infrastructure.sqlite.connection import SqliteDatabase
        from api.communications.attestations import send_attestation_api
        from api.communications.schemas import AttestationSend

        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_attestation.db")
        orig_db_path = SqliteDatabase.get_db_path()
        try:
            SqliteDatabase.set_db_path(db_path)
            SqliteDatabase.setup_database()
            conn = SqliteDatabase.get_connection()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO seasons (id, name, is_active) VALUES (1, '2026-2027', 1)")
            c.execute("""
                INSERT INTO users (id, last_name, first_name, last_name_key, first_name_key, email_primary, birth_date)
                VALUES (10, 'DUPONT', 'Jean', 'dupont', 'jean', 'jean.dupont@example.com', '1990-01-01')
            """)
            c.execute("""
                INSERT INTO orders (id, season_id, order_ref, order_date, payer_first_name, payer_last_name, payer_email)
                VALUES (20, 1, 'CMD-TEST-ATT', '2026-09-15', 'Jean', 'Dupont', 'jean.dupont@example.com')
            """)
            c.execute("""
                INSERT INTO purchases (id, order_id, user_id, tarif_name, amount, status)
                VALUES (30, 20, 10, 'Adulte', 180.0, 'Payé')
            """)
            conn.commit()
            conn.close()

            # The member, its amount and payer are read from the database: only the purchase is sent
            payload = AttestationSend(purchase_id=30, season="2026-2027", to_email="jean.dupont@example.com")

            with patch("infrastructure.mail.repository.EmailRepository.send_email", return_value=True) as mock_send:
                res = send_attestation_api(payload)

            self.assertEqual(res.status, "success")
            self.assertTrue(res.email_sent_date)

            # Vérifier les paramètres de l'envoi d'e-mail (conforme desktop)
            mock_send.assert_called_once()
            _, kwargs = mock_send.call_args
            self.assertEqual(kwargs.get("from_email"), "inscription@alj-escalade.fr")
            self.assertEqual(kwargs.get("from_name"), "Amicale Laïque Jonage - Inscriptions")
            self.assertIn("Attestation de paiement", kwargs.get("subject", ""))
            self.assertIsNotNone(kwargs.get("html_body"))
            self.assertIn("Amicale Laïque", kwargs.get("html_body", ""))

            # Vérifier que la date est enregistrée en base SQLite
            conn = SqliteDatabase.get_connection()
            row = conn.execute("SELECT email_sent_date FROM purchases WHERE id = 30").fetchone()
            conn.close()
            self.assertIsNotNone(row["email_sent_date"])
            self.assertEqual(row["email_sent_date"], res.email_sent_date)
        finally:
            SqliteDatabase.set_db_path(orig_db_path)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_member_add_requires_admin_role(self):
        """Les endpoints de création manuelle d'adhérents exigent le rôle admin."""
        from infrastructure.security.api_auth import required_role
        self.assertEqual(required_role("POST", "/api/members/create"), Role.ADMIN)
        self.assertEqual(required_role("POST", "/api/members/add"), Role.ADMIN)

    def test_member_add_endpoint_and_sqlite_persistence(self):
        """add_member_api persiste le nouvel adhérent, la commande et l'achat dans SQLite."""
        import tempfile
        import shutil
        from infrastructure.sqlite.connection import SqliteDatabase
        from api.members.members import add_member_api
        from api.members.schemas import MemberCreate

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
                    "emergency1_name": "VALENTIN Marc",
                    "emergency1_phone": "06 99 88 77 66",
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
            self.assertEqual(u["emergency1_name"], "VALENTIN Marc")
            self.assertEqual(u["emergency1_phone"], "06 99 88 77 66")

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
        import tempfile
        import shutil
        from infrastructure.sqlite.connection import SqliteDatabase
        from api.members.members import update_member_api
        from api.members.schemas import MemberUpdate

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

    def test_season_tarifs_endpoint(self):
        """GET /api/season-tarifs retourne les tarifs disponibles de la saison active."""
        res = TestClient(app).get("/api/season-tarifs", params={"season": "2026-2027"}).json()
        self.assertEqual((res["status"], res["season"]), ("success", "2026-2027"))
        self.assertIn("Licence sèche", res["tarifs"])

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
        expected = {**new_slot, "id": saved_id, "encadrants": ["Test Coach"], "whatsapp_link": "", "naissance_min": "", "naissance_max": ""}
        self.assertEqual(res_create["item"], expected)

        # 2. Modification du créneau
        res_update = client.post("/api/planning/item", json={**expected, "groupe": "Test Créneau Modifié Web"})
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(client.get("/api/planning").json(), [{**expected, "groupe": "Test Créneau Modifié Web"}])

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

    def _temp_database(self, name):
        """SqliteDatabase on an empty database for the test."""
        from infrastructure.sqlite.connection import SqliteDatabase
        temp_dir = tempfile.mkdtemp()
        orig_db_path = SqliteDatabase.get_db_path()
        SqliteDatabase.set_db_path(os.path.join(temp_dir, name))
        SqliteDatabase.setup_database()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        self.addCleanup(SqliteDatabase.set_db_path, orig_db_path)

    def test_email_template_crud_endpoints_and_sqlite(self):
        """POST, GET et DELETE /api/email-templates modifient correctement SQLite."""
        self._temp_database("test_tpl.db")
        client = TestClient(app)

        def names():
            return [t["name"] for t in client.get("/api/email-templates").json()["templates"]]

        # 1. Création d'un nouveau modèle
        payload = {
            "name": "Test Nouveau Modèle",
            "subject": "Sujet de test personnalisé",
            "body": "Bonjour {first_name}, corps de test.",
            "sender_email": "test@alj-escalade.fr",
            "sender_name": "ALJ Test"
        }
        res_save = client.post("/api/email-templates", json=payload).json()
        self.assertEqual(res_save["status"], "success")
        self.assertEqual(res_save["template"], payload)
        self.assertIn("Test Nouveau Modèle", names())

        # 2. Renommage du modèle (old_name -> name)
        rename_payload = {**payload, "name": "Test Modèle Renommé", "old_name": "Test Nouveau Modèle", "subject": "Sujet mis à jour"}
        self.assertEqual(client.post("/api/email-templates", json=rename_payload).json()["status"], "success")
        self.assertIn("Test Modèle Renommé", names())
        self.assertNotIn("Test Nouveau Modèle", names())

        # 3. Suppression du modèle
        res_del = client.delete("/api/email-templates/Test Modèle Renommé")
        self.assertEqual(res_del.json()["status"], "success")
        self.assertNotIn("Test Modèle Renommé", names())
        self.assertEqual(client.delete("/api/email-templates/Test Modèle Renommé").status_code, 404)

    def test_email_template_save_refusals(self):
        """Nom, sujet, adresse d'expédition et doublons sont vérifiés par le serveur."""
        self._temp_database("test_tpl_refusals.db")
        client = TestClient(app)
        base = {"name": "Relance", "subject": "Sujet", "body": "Corps"}
        self.assertEqual(client.post("/api/email-templates", json=base).status_code, 200)
        client.post("/api/email-templates", json={**base, "name": "Autre"})

        for body, status, message in (
            ({**base, "name": " "}, 400, "Le nom du modèle est obligatoire."),
            ({**base, "subject": ""}, 400, "Le sujet du modèle est obligatoire."),
            ({**base, "sender_email": "pas-une-adresse"}, 400, "L'adresse d'expédition doit être une adresse e-mail valide."),
            # A new template, or a rename, onto an existing name (case ignored)
            ({**base, "name": "RELANCE"}, 409, "Un modèle nommé « RELANCE » existe déjà."),
            ({**base, "name": "autre", "old_name": "Relance"}, 409, "Un modèle nommé « autre » existe déjà."),
        ):
            with self.subTest(body=body):
                r = client.post("/api/email-templates", json=body)
                self.assertEqual(r.status_code, status)
                self.assertEqual(r.json()["message"], message)
        # Saving a template under its own name, or changing the case of it, is fine
        self.assertEqual(client.post("/api/email-templates", json={**base, "old_name": "Relance"}).status_code, 200)
        self.assertEqual(client.post("/api/email-templates", json={**base, "name": "RELANCE", "old_name": "Relance"}).status_code, 200)
        # An empty sender falls back to the club's address
        saved = client.post("/api/email-templates", json={**base, "name": "Défaut"}).json()["template"]
        self.assertEqual(saved["sender_email"], "inscription@alj-escalade.fr")
        listed = client.get("/api/email-templates").json()
        self.assertEqual(listed["templates"][0]["sender_email"], "inscription@alj-escalade.fr")
        # The Vue app takes the club's sender settings from this answer instead of its own copy
        self.assertEqual(listed["default_sender_email"], "inscription@alj-escalade.fr")
        self.assertEqual(listed["default_sender_name"], "Amicale Laïque Jonage - Inscriptions")
        self.assertIn("contact@alj-escalade.fr", listed["sender_suggestions"])
        self.assertEqual(listed["club_contact_email"], "contact@alj-escalade.fr")

    def test_whatsapp_template_endpoints(self):
        """GET et POST /api/whatsapp-template enregistrent et lisent le texte WhatsApp."""
        from support.fake_firestore import use_fake_firestore
        use_fake_firestore(self)
        client = TestClient(app)
        self.assertEqual(client.get("/api/whatsapp-template").json(), {"status": "success", "template": ""})

        res_save = client.post("/api/whatsapp-template", json={"template": "Rejoignez le groupe WhatsApp du club : https://chat.whatsapp.com/xxx"})
        self.assertEqual(res_save.json()["status"], "success")
        self.assertIn("chat.whatsapp.com", client.get("/api/whatsapp-template").json()["template"])
        self.assertEqual(client.post("/api/whatsapp-template", json={"template": "  "}).status_code, 400)

    def test_email_template_write_requires_admin_role(self):
        """Les modifications de templates d'emails exigent le rôle admin."""
        from infrastructure.security.api_auth import required_role
        self.assertEqual(required_role("POST", "/api/email-templates"), Role.ADMIN)
        self.assertEqual(required_role("DELETE", "/api/email-templates/Test"), Role.ADMIN)
        self.assertEqual(required_role("POST", "/api/whatsapp-template"), Role.ADMIN)
        self.assertEqual(required_role("GET", "/api/email-templates"), Role.COACH)

    def test_apply_template_variables_adherents_extension(self):
        """Les variables {tarif} et {season} sont correctement résolues pour les adhérents."""
        from domain.email_personalization import apply_template_variables
        member = {
            "first_name": "camille",
            "last_name": "durand",
            "licence_ffme": "654321",
            "tarif_name": "Jeunes 2010",
            "season_name": "2026-2027"
        }
        text = "Bonjour {first_name} {Nom}, votre inscription au groupe {tarif} pour la saison {season} (licence {num_licence}) est validée."
        rendered = apply_template_variables(text, member)
        self.assertEqual(
            rendered,
            "Bonjour Camille DURAND, votre inscription au groupe Jeunes 2010 pour la saison 2026-2027 (licence 654321) est validée."
        )


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
                     "/bureau/outils/helloasso-import", "/bureau/parametres/campagnes"):
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
