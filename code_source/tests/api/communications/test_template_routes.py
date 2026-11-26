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
        self.assertEqual(res_save["template"], {**payload, "kind": "adherent", "is_default": False, "needs_fixing": False})
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

    def test_save_stores_variables_as_keys_and_refuses_unknown_ones(self):
        """Labels, lenient spellings and former names are stored as keys; an unknown variable is refused."""
        self._temp_database("test_tpl_variables.db")
        client = TestClient(app)
        payload = {"name": "Relance", "subject": "Rappel { prénom }", "body": "Bonjour {Prénom} {NOM},\n{bloc_whatsapp}",
                   "kind": "competition"}
        saved = client.post("/api/email-templates", json=payload).json()["template"]
        self.assertEqual(saved["subject"], "Rappel {first_name}")
        self.assertEqual(saved["body"], "Bonjour {first_name} {last_name},\n"
                                        "Voici le lien du groupe WhatsApp dédié à cette compétition : {whatsapp_link}")
        stored = next(t for t in client.get("/api/email-templates").json()["templates"] if t["name"] == "Relance")
        self.assertEqual(stored["body"], saved["body"])

        refused = client.post("/api/email-templates", json={**payload, "body": "Bonjour {Prenon}"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("{Prenon}", refused.json()["message"])
        self.assertIn("{Prénom}", refused.json()["message"])

    def test_templates_have_a_kind_saved_or_inferred_from_their_name(self):
        """A template saved before kinds existed gets one from its name; a saved kind is kept; the variables must
        belong to the kind."""
        self._temp_database("test_tpl_kinds.db")
        client = TestClient(app)

        def listed():
            return {t["name"]: t for t in client.get("/api/email-templates").json()["templates"]}

        shipped = listed()
        self.assertEqual(shipped["Compétition - 1er Inscription"]["kind"], "competition")
        self.assertEqual(shipped["Attestation échéance"]["kind"], "attestation")
        self.assertEqual(shipped["Relance inscription"]["kind"], "adherent")
        self.assertFalse(shipped["Relance inscription"]["needs_fixing"])

        client.post("/api/email-templates", json={"name": "Infos", "subject": "Infos", "body": "{Nom de la compétition}",
                                                  "kind": "competition"})
        client.post("/api/email-templates", json={"name": "Attestation 2", "subject": "A", "body": "{Montant de l'adhésion}"})
        self.assertEqual((listed()["Infos"]["kind"], listed()["Attestation 2"]["kind"]), ("competition", "attestation"))

        refused = client.post("/api/email-templates", json={"name": "Infos", "old_name": "Infos", "subject": "Infos",
                                                            "body": "{Nom de la compétition}", "kind": "adherent"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("Variable non disponible pour un modèle Adhérent : {Nom de la compétition}.", refused.json()["message"])

    def test_one_default_template_per_kind(self):
        """Marking a default unmarks the previous one of its kind; a rename keeps the mark, a kind change drops it."""
        self._temp_database("test_tpl_default.db")
        client = TestClient(app)

        def defaults():
            return sorted((t["kind"], t["name"]) for t in client.get("/api/email-templates").json()["templates"] if t["is_default"])

        def save(**fields):
            response = client.post("/api/email-templates", json={"subject": "Sujet", "body": "Bonjour", **fields})
            self.assertEqual(response.status_code, 200, response.text)

        self.assertEqual(defaults(), [])
        save(name="A", kind="adherent", is_default=True)
        save(name="B", kind="adherent", is_default=True)
        save(name="C", kind="competition", is_default=True)
        self.assertEqual(defaults(), [("adherent", "B"), ("competition", "C")])

        save(name="B2", old_name="B", kind="adherent")  # renamed, default kept
        self.assertEqual(defaults(), [("adherent", "B2"), ("competition", "C")])
        save(name="C", old_name="C", kind="attestation")  # another kind: no longer a default
        self.assertEqual(defaults(), [("adherent", "B2")])
        save(name="B2", old_name="B2", kind="adherent", is_default=False)
        self.assertEqual(defaults(), [])

    def test_templates_with_former_or_foreign_variables_need_fixing(self):
        self._temp_database("test_tpl_fixing.db")
        from infrastructure.sqlite.email_templates import EmailTemplateRepository
        EmailTemplateRepository.save_email_template("Vieux", "Sujet {Prénom}", "Lien : {whatapp_Id} {competition_deadline}")
        template = next(t for t in TestClient(app).get("/api/email-templates").json()["templates"] if t["name"] == "Vieux")
        self.assertEqual(template["kind"], "adherent")
        self.assertTrue(template["needs_fixing"])

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
        from domain.communications.email_personalization import apply_template_variables
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
