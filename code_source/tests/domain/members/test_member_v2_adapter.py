import os
import sys
import unittest

# Ajustement du chemin pour importer les modules depuis 'src'
_test_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src_dir = os.path.join(os.path.dirname(_test_dir), "src") if os.path.basename(_test_dir) == "tests" else _test_dir
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from domain.members.models import Member
from domain.members.sex import Sex
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.members import MemberRepository


class TestMemberBilingualAdapter(unittest.TestCase):
    """Phase 4 — Member.from_dict lit les noms v2 (prioritaires) et les libellés legacy (repli)."""

    def test_from_dict_v2_names(self):
        m = Member.from_dict({
            "order_ref": "A1", "status": "Validated", "tarif_name": "Loisir", "amount": 150.0,
            "last_name": "MARTIN", "first_name": "Leo",
            "payer_last_name": "MARTIN", "payer_first_name": "Paul", "payer_email": "paul@ex.fr",
            "birth_date": "1990-05-10",
            "email_primary": "leo@ex.fr", "email_secondary": "leo2@ex.fr",
            "emergency1_name": "MARIE Martin", "emergency1_phone": "0600000001",
            "licence_ffme": "123456",
            "purchase_options": [
                {"option_name": "Assurance Base", "amount": 45.0},
                {"option_name": "Assurance Option VTT", "amount": 12.0},
            ],
        })
        self.assertEqual(m.user_last_name, "MARTIN")
        self.assertEqual(m.user_first_name, "Leo")
        self.assertEqual(m.payer_email, "paul@ex.fr")
        self.assertEqual(m.birth_date, "1990-05-10")
        self.assertEqual(m.primary_email, "leo@ex.fr")
        self.assertEqual(m.secondary_email, "leo2@ex.fr")
        self.assertEqual(m.emergency_contact_name_1, "MARIE Martin")
        self.assertEqual(m.licence_ffme, "123456")
        self.assertTrue(m.insurance.has_base)
        self.assertEqual(m.insurance.amount_base, 45.0)
        self.assertTrue(m.insurance.has_vtt)
        self.assertFalse(m.insurance.has_ski)

    def test_from_dict_legacy_names(self):
        m = Member.from_dict({
            "order_ref": "B2", "status": "Validé", "tarif_name": "Adultes", "amount": 155.0,
            "user_lastName": "DUPONT", "user_firstName": "Jean",
            "payer_lastName": "DUPONT", "payer_firstName": "Jean", "payer_email": "j@ex.fr",
            "champ_Date de naissance de l'adhérent": "15/03/1980",
            "champ_Adresse mail pour la réception des informations du club": "jean@ex.fr",
            "champ_Numéro de Licence FFME (6 chiffres)": "654321.0",
            "opt_Assurance Base": "Oui", "opt_Montant Assurance Base": 40.0,
        })
        self.assertEqual(m.user_last_name, "DUPONT")
        self.assertEqual(m.birth_date, "15/03/1980")
        self.assertEqual(m.primary_email, "jean@ex.fr")
        self.assertEqual(m.licence_ffme, "654321")
        self.assertTrue(m.insurance.has_base)
        self.assertEqual(m.insurance.amount_base, 40.0)

    def test_from_dict_v2_priority_over_legacy(self):
        # Les deux formats présents : le nom v2 gagne
        m = Member.from_dict({"last_name": "V2NOM", "user_lastName": "LEGACYNOM"})
        self.assertEqual(m.user_last_name, "V2NOM")

    def test_from_dict_empty_values_fall_back(self):
        # Nom v2 vide -> repli legacy
        m = Member.from_dict({"last_name": "", "user_lastName": "LEGACYNOM"})
        self.assertEqual(m.user_last_name, "LEGACYNOM")

    def test_from_dict_sex_column(self):
        self.assertEqual(Member.from_dict({"sex": "F"}).sex, Sex.FEMALE)
        self.assertEqual(Member.from_dict({"sex": "F"}).to_dict()["champ_Sexe"], "F")

    def test_from_dict_sex_from_legacy_gender(self):
        # Rows and documents written before the rename hold `gender` (free text)
        self.assertEqual(Member.from_dict({"gender": "Homme"}).sex, Sex.MALE)

    def test_from_dict_sex_from_helloasso_label(self):
        self.assertEqual(Member.from_dict({"champ_Sexe": "Féminin"}).sex, Sex.FEMALE)

    def test_from_dict_sex_missing(self):
        m = Member.from_dict({"order_ref": "C3"})
        self.assertIsNone(m.sex)
        self.assertEqual(m.to_dict()["champ_Sexe"], "")

    def test_from_dict_sex_unparseable_logged(self):
        with self.assertLogs("alj", level="WARNING") as logs:
            m = Member.from_dict({"order_ref": "C4", "last_name": "SECRET", "champ_Sexe": "X"})
        self.assertIsNone(m.sex)
        self.assertIn("C4", logs.output[0])
        self.assertNotIn("SECRET", logs.output[0])  # no personal data in the logs


class TestGetMembersLoader(unittest.TestCase):

    def setUp(self):
        self.original_db_path = SqliteDatabase.get_db_path()
        self.test_db_path = os.path.join(_test_dir, "test_get_members.db")
        SqliteDatabase.set_db_path(self.test_db_path)

    def tearDown(self):
        SqliteDatabase.set_db_path(self.original_db_path)
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def test_get_members_returns_typed_members(self):
        membre = {
            "order_ref": "GM1", "order_date": "2026-08-31T10:00:00", "status": "Validated",
            "tarif_name": "Loisir - Adultes", "amount": 150.0,
            "user_lastName": "GETMEMBER", "user_firstName": "Zoe",
            "payer_lastName": "GETMEMBER", "payer_firstName": "Papa", "payer_email": "papa@ex.fr",
            "champ_Date de naissance de l'adhérent": "1992-02-02",
            "champ_Adresse mail pour la réception des informations du club": "zoe@ex.fr",
            "opt_Assurance Base": "Oui", "opt_Montant Assurance Base": 45.0,
        }
        MemberRepository.upsert_members([membre])
        members = MemberRepository.get_members(season_filter="2026-2027")
        targets = [m for m in members if m.user_last_name == "GETMEMBER"]
        self.assertEqual(len(targets), 1)
        m = targets[0]
        self.assertIsInstance(m, Member)
        self.assertEqual(m.user_first_name, "Zoe")
        # Le payeur écrit depuis la phase 3 est visible côté lecture
        self.assertEqual(m.payer_email, "papa@ex.fr")
        self.assertTrue(m.insurance.has_base)


if __name__ == "__main__":
    unittest.main()
