"""Attestations: the document rules and the admin-only preview and send routes."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from infrastructure.security.api_auth import Role


class TestAttestationRoutes(unittest.TestCase):
    def _temp_database(self, name):
        """SqliteDatabase on an empty database for the test."""
        from infrastructure.sqlite.connection import SqliteDatabase
        temp_dir = tempfile.mkdtemp()
        orig_db_path = SqliteDatabase.get_db_path()
        SqliteDatabase.set_db_path(os.path.join(temp_dir, name))
        SqliteDatabase.setup_database()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        self.addCleanup(SqliteDatabase.set_db_path, orig_db_path)

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
        import shutil
        import tempfile

        from infrastructure.sqlite.connection import SqliteDatabase
        from services.communications import email_log
        from services.communications.attestations import send_attestation

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
            with patch("infrastructure.mail.sender.EmailSender.send_email", return_value=True) as mock_send:
                res = send_attestation("2026-2027", 30, "jean.dupont@example.com", "admin@alj.example")

            self.assertTrue(res["email_sent_date"])
            (entry,) = email_log.current_store().entries
            self.assertEqual((entry["kind"], entry["author"], entry["member_ids"]), ("attestation", "admin@alj.example", [10]))
            self.assertEqual([(r["email"], r["status"]) for r in entry["recipients"]], [("jean.dupont@example.com", "sent")])

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
            self.assertEqual(row["email_sent_date"], res["email_sent_date"])
        finally:
            SqliteDatabase.set_db_path(orig_db_path)
            shutil.rmtree(temp_dir, ignore_errors=True)
