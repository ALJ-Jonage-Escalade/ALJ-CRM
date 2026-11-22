"""E-mail and WhatsApp templates: saved by admins, their variables replaced."""

import os
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from infrastructure.security.api_auth import Role
from server import app


class TestTemplateRoutes(unittest.TestCase):
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

    def test_variables_route_lists_each_variable_with_its_label_kinds_and_aliases(self):
        """GET /api/email-templates/variables: the registry, for admins only."""
        from infrastructure.security.api_auth import required_role
        variables = {v["key"]: v for v in TestClient(app).get("/api/email-templates/variables").json()["variables"]}
        self.assertEqual(variables["first_name"]["label"], "Prénom")
        self.assertEqual(variables["amount"]["kinds"], ["adherent", "attestation"])
        self.assertEqual(variables["name_competition"]["aliases"], ["nom_competition"])
        self.assertIn("bloc_whatsapp", variables["whatsapp_link"]["aliases"])
        self.assertEqual(variables["montant_competition"]["demo"], "15,50")
        self.assertEqual(required_role("GET", "/api/email-templates/variables"), Role.ADMIN)

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
