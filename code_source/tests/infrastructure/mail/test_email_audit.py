"""EmailSender's audit log of the sends."""

import json
import os
import tempfile
import unittest

from infrastructure.mail.sender import EmailSender
from infrastructure.sqlite.connection import SqliteDatabase


class TestEmailAudit(unittest.TestCase):
    def setUp(self):
        # Sauvegarder le chemin de la BDD d'origine
        self.original_db_path = SqliteDatabase.get_db_path()
        self._tmp = tempfile.TemporaryDirectory()
        self.test_db_path = os.path.join(self._tmp.name, "test_database.db")
        SqliteDatabase.set_db_path(self.test_db_path)

    def tearDown(self):
        # Restaurer la BDD d'origine
        SqliteDatabase.set_db_path(self.original_db_path)
        self._tmp.cleanup()

    def test_email_repository_audit_logging(self):
        """Vérifie que la journalisation d'audit des e-mails fonctionne correctement."""
        test_dest = "audit_test@escalade.fr"
        test_subj = "Test Audit Subject"
        
        # Supprimer le journal temporairement pour le test ou vérifier l'ajout
        if os.path.exists(EmailSender.audit_file_path()):
            try:
                os.remove(EmailSender.audit_file_path())
            except OSError:
                pass
                
        EmailSender.log_audit(test_dest, test_subj, "SUCCESS")
        
        self.assertTrue(os.path.exists(EmailSender.audit_file_path()))
        
        with open(EmailSender.audit_file_path(), "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        self.assertTrue(len(lines) > 0)
        last_log = json.loads(lines[-1].strip())
        self.assertEqual(last_log["to"], test_dest)
        self.assertEqual(last_log["subject"], test_subj)
        self.assertEqual(last_log["status"], "SUCCESS")
        
        # Nettoyage
        try:
            os.remove(EmailSender.audit_file_path())
        except OSError:
            pass
