import os
import sys
import unittest
import json

# Ajustement du chemin pour importer les modules depuis 'src'
_test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(os.path.dirname(_test_dir), "src") if os.path.basename(_test_dir) == "tests" else _test_dir
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from infrastructure.security.secret_store import SecretStore
from infrastructure.mail.repository import EmailRepository
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.members import MemberRepository

class TestInfrastructureLot2(unittest.TestCase):

    def setUp(self):
        # Sauvegarder le chemin de la BDD d'origine
        self.original_db_path = SqliteDatabase.get_db_path()
        # Configurer un chemin temporaire pour les tests
        self.test_db_path = os.path.join(_test_dir, "test_database.db")
        SqliteDatabase.set_db_path(self.test_db_path)
        
    def tearDown(self):
        # Restaurer la BDD d'origine
        SqliteDatabase.set_db_path(self.original_db_path)
        # Supprimer le fichier de test s'il existe
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def test_sqlite_repository_crud(self):
        """Vérifie le cycle de vie complet des données (CRUD) avec MemberRepository."""
        # 1. Initialisation de la BDD
        SqliteDatabase.setup_database()
        self.assertTrue(os.path.exists(self.test_db_path))
        
        # 2. Insertion de membres (Create/Upsert)
        test_member = {
            "order_ref": "99999",
            "order_date": "2026-08-16T14:30:00",
            "status": "Validated",
            "tarif_name": "Adultes autonomes",
            "amount": 150.0,
            "user_lastName": "DUPONT",
            "user_firstName": "Jean",
            "payer_lastName": "DUPONT",
            "payer_firstName": "Jean",
            "payer_email": "jean.dupont@test.com",
            "champ_Date de naissance de l'adhérent": "1990-05-15",
            "champ_Sexe": "M",
            "champ_Nationalité": "Française",
            "champ_Adresse : numéro et nom de rue": "10 Rue des Fleurs",
            "champ_Code postal": "69000",
            "champ_Ville": "Lyon",
            "champ_Pays": "France",
            "champ_Téléphone ": "0612345678",
            "champ_Adresse mail pour la réception des informations du club": "jean.dupont@test.com",
            "is_modified": "Non",
            "commentaires_correctif": ""
        }
        
        inserted = MemberRepository.upsert_members([test_member])
        self.assertEqual(inserted, 1)
        
        # 3. Chargement des membres (Read)
        loaded = MemberRepository.load_direct_data("2026-2027")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["last_name"], "DUPONT")
        self.assertEqual(loaded[0]["first_name"], "Jean")
        self.assertEqual(loaded[0]["amount"], 150.0)

    def test_secret_store_set_get(self):
        """Vérifie le stockage et la récupération de secrets via SecretStore."""
        test_key = "ALJ_TEST_SECRET_KEY"
        test_value = "SecrEtValue-12345!"
        
        SecretStore.set_secret(test_key, test_value)
        
        retrieved = SecretStore.get_secret(test_key)
        self.assertEqual(retrieved, test_value)
        
        # Nettoyage de la clé temporaire du .env s'il a été écrit
        env_path = os.path.join(os.path.dirname(_test_dir), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = [line for line in lines if not line.startswith(f"{test_key}=")]
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            except OSError:
                pass

    def test_email_repository_audit_logging(self):
        """Vérifie que la journalisation d'audit des e-mails fonctionne correctement."""
        test_dest = "audit_test@escalade.fr"
        test_subj = "Test Audit Subject"
        
        # Supprimer le journal temporairement pour le test ou vérifier l'ajout
        if os.path.exists(EmailRepository.audit_file_path()):
            try:
                os.remove(EmailRepository.audit_file_path())
            except OSError:
                pass
                
        EmailRepository.log_audit(test_dest, test_subj, "SUCCESS")
        
        self.assertTrue(os.path.exists(EmailRepository.audit_file_path()))
        
        with open(EmailRepository.audit_file_path(), "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        self.assertTrue(len(lines) > 0)
        last_log = json.loads(lines[-1].strip())
        self.assertEqual(last_log["to"], test_dest)
        self.assertEqual(last_log["subject"], test_subj)
        self.assertEqual(last_log["status"], "SUCCESS")
        
        # Nettoyage
        try:
            os.remove(EmailRepository.audit_file_path())
        except OSError:
            pass



    def test_already_member_detection(self):
        """Vérifie la détection automatique de la réinscription d'un adhérent (déjà adhérent dans une autre saison)."""
        SqliteDatabase.setup_database()
        
        # Adhérent réinscrit (présent en 25/26 et en 26/27)
        member_historic = {
            "order_ref": "HIST-001",
            "order_date": "2025-09-01",
            "status": "Validated",
            "tarif_name": "Loisir Collège",
            "amount": 160.0,
            "user_lastName": "MARTINEZ",
            "user_firstName": "Carlos"
        }
        
        # Insérer d'abord dans l'ancienne saison
        MemberRepository.upsert_members([member_historic], "2025-2026")
        
        # Insérer maintenant le même adhérent dans la nouvelle saison
        member_new = {
            "order_ref": "NEW-001",
            "order_date": "2026-09-01",
            "status": "Validated",
            "tarif_name": "Séance autonome",
            "amount": 120.0,
            "user_lastName": "MARTINEZ",
            "user_firstName": "Carlos"
        }
        MemberRepository.upsert_members([member_new], "2026-2027")
        
        # Adhérent complètement nouveau (uniquement en 26/27)
        member_unique = {
            "order_ref": "NEW-999",
            "order_date": "2026-09-10",
            "status": "Validated",
            "tarif_name": "Enfant",
            "amount": 150.0,
            "user_lastName": "LORENZO",
            "user_firstName": "Ines"
        }
        MemberRepository.upsert_members([member_unique], "2026-2027")
        
        # Charger les données pour la saison active 2026-2027
        loaded_raw = MemberRepository.load_direct_data("2026-2027")
        self.assertEqual(len(loaded_raw), 2)
        
        carlos = next(row for row in loaded_raw if row["last_name"] == "MARTINEZ")
        ines = next(row for row in loaded_raw if row["last_name"] == "LORENZO")

        # Carlos était déjà adhérent dans l'autre saison ; Ines est complètement nouvelle
        self.assertGreater(int(carlos["already_member"] or 0), 0)
        self.assertEqual(int(ines["already_member"] or 0), 0)


    def test_upsert_members_status_priority(self):
        """Vérifie que upsert_members préserve les statuts prioritaires (Processed > Canceled)."""
        SqliteDatabase.setup_database()
        
        # 1. Commande active
        member_active = {
            "order_ref": "ORD-ACTIVE-123",
            "order_date": "2026-06-13T09:21:07",
            "tarif_name": "Loisir cours",
            "amount": 246.0,
            "status": "Processed",
            "user_lastName": "CLAPET_TEST",
            "user_firstName": "Mathilde"
        }
        MemberRepository.upsert_members([member_active], "2026-2027")
        
        # Charger et vérifier que c'est bien actif
        loaded = MemberRepository.load_direct_data("2026-2027")
        match = next(m for m in loaded if m["last_name"] == "CLAPET_TEST")
        self.assertEqual(match["status"], "Processed")
        self.assertEqual(match["order_ref"], "ORD-ACTIVE-123")
        
        # 2. Tenter d'écraser avec une commande annulée
        member_canceled = {
            "order_ref": "ORD-CANCELED-456",
            "order_date": "2026-06-13T09:07:28",
            "tarif_name": "Liste d'attente",
            "amount": 0.0,
            "status": "Canceled",
            "user_lastName": "CLAPET_TEST",
            "user_firstName": "Mathilde"
        }
        MemberRepository.upsert_members([member_canceled], "2026-2027")
        
        # Vérifier que la commande active a été CONSERVÉE (priorité supérieure)
        loaded = MemberRepository.load_direct_data("2026-2027")
        match = next(m for m in loaded if m["last_name"] == "CLAPET_TEST")
        self.assertEqual(match["status"], "Processed")
        self.assertEqual(match["order_ref"], "ORD-ACTIVE-123")
        self.assertEqual(float(match["amount"]), 246.0)

        # 3. À l'inverse, si on part d'une annulée et qu'on upsert une active, elle doit écraser !
        # Créer un autre membre de test
        m_canceled = {
            "order_ref": "ORD-CANCELED-999",
            "order_date": "2026-06-13T09:07:28",
            "tarif_name": "Liste d'attente",
            "amount": 0.0,
            "status": "Canceled",
            "user_lastName": "CLAPET_TEST2",
            "user_firstName": "Mathilde"
        }
        MemberRepository.upsert_members([m_canceled], "2026-2027")
        
        # Vérifier qu'il est bien Canceled
        loaded = MemberRepository.load_direct_data("2026-2027")
        match = next(m for m in loaded if m["last_name"] == "CLAPET_TEST2")
        self.assertEqual(match["status"], "Canceled")
        
        # Upserter la version active
        m_active = {
            "order_ref": "ORD-ACTIVE-888",
            "order_date": "2026-06-13T09:21:07",
            "tarif_name": "Loisir cours",
            "amount": 246.0,
            "status": "Processed",
            "user_lastName": "CLAPET_TEST2",
            "user_firstName": "Mathilde"
        }
        MemberRepository.upsert_members([m_active], "2026-2027")
        
        # Vérifier qu'il a bien été mis à jour à Processed
        loaded = MemberRepository.load_direct_data("2026-2027")
        match = next(m for m in loaded if m["last_name"] == "CLAPET_TEST2")
        self.assertEqual(match["status"], "Processed")
        self.assertEqual(match["order_ref"], "ORD-ACTIVE-888")

if __name__ == "__main__":
    unittest.main()
