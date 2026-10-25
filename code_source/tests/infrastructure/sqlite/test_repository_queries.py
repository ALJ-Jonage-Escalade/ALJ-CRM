"""Tests for the SQLite repository queries that replaced raw SQL in services and pages."""
import os
import sys
import unittest

_test_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src_dir = os.path.join(os.path.dirname(_test_dir), "src") if os.path.basename(_test_dir) == "tests" else _test_dir
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.geocache import GeocacheRepository
from infrastructure.sqlite.members import MemberRepository
from infrastructure.sqlite.seasons import SeasonRepository

BASE_MEMBER = {
    "order_date": "2026-09-01T10:00:00",
    "status": "Validated",
    "amount": 150.0,
    "payer_lastName": "MARTIN",
    "payer_firstName": "Claire",
    "champ_Date de naissance de l'adhérent": "2017-03-10",
    "is_modified": "Non",
    "commentaires_correctif": "",
}


class TestRepositoryQueries(unittest.TestCase):

    def setUp(self):
        self.original_db_path = SqliteDatabase.get_db_path()
        self.test_db_path = os.path.join(_test_dir, "test_repository_queries.db")
        SqliteDatabase.set_db_path(self.test_db_path)
        SqliteDatabase.setup_database()

    def tearDown(self):
        SqliteDatabase.set_db_path(self.original_db_path)
        SqliteDatabase._database_setup_done = False
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(self.test_db_path + suffix):
                try:
                    os.remove(self.test_db_path + suffix)
                except OSError:
                    pass

    def _seed(self, ref, first_name, last_name, tarif, payer_email):
        member = dict(BASE_MEMBER, order_ref=ref, user_firstName=first_name, user_lastName=last_name,
                      tarif_name=tarif, payer_email=payer_email)
        MemberRepository.upsert_members([member])

    def _user_id(self, first_name):
        conn = SqliteDatabase.get_connection()
        try:
            return conn.execute("SELECT id FROM users WHERE first_name = ?", (first_name,)).fetchone()["id"]
        finally:
            conn.close()

    def test_get_all_tarifs_is_sorted_and_distinct(self):
        self._seed("1", "Léo", "MARTIN", "Loisir", "a@test.com")
        self._seed("2", "Zoé", "DURAND", "Adultes", "b@test.com")
        self._seed("3", "Max", "PETIT", "Loisir", "c@test.com")
        self.assertEqual(SeasonRepository.get_all_tarifs(), ["Adultes", "Loisir"])

    def test_list_contact_emails_includes_users_and_payers(self):
        self._seed("1", "Léo", "MARTIN", "Loisir", "Payer@Test.com")
        conn = SqliteDatabase.get_connection()
        conn.execute("UPDATE users SET email_primary = ' Leo@Test.com ', email_secondary = ''")
        conn.commit()
        conn.close()
        emails = MemberRepository.list_contact_emails()
        self.assertIn("payer@test.com", emails)
        self.assertIn("leo@test.com", emails)
        self.assertNotIn("", emails)

    def test_get_users_by_ids_returns_only_requested(self):
        self._seed("1", "Léo", "MARTIN", "Loisir", "a@test.com")
        self._seed("2", "Zoé", "DURAND", "Loisir", "b@test.com")
        leo = self._user_id("Léo")
        users = MemberRepository.get_users_by_ids([leo, leo, 999999])
        self.assertEqual(list(users), [leo])
        self.assertEqual(users[leo]["last_name"], "MARTIN")
        self.assertIsInstance(users[leo], dict)
        self.assertEqual(MemberRepository.get_users_by_ids([]), {})

    def test_correct_member_address_updates_user_and_geocache(self):
        self._seed("1", "Léo", "MARTIN", "Loisir", "a@test.com")
        MemberRepository.correct_member_address(
            " léo", "martin ", "1 rue de la Paix", "75001", "Paris",
            ("1 rue de la Paix, 75001, PARIS, France", 48.86, 2.33),
        )
        conn = SqliteDatabase.get_connection()
        row = conn.execute("SELECT address, zip_code, city FROM users WHERE id = ?",
                           (self._user_id("Léo"),)).fetchone()
        conn.close()
        self.assertEqual(tuple(row), ("1 rue de la Paix", "75001", "Paris"))
        self.assertEqual(GeocacheRepository.get_geocache()["1 rue de la Paix, 75001, PARIS, France"], [48.86, 2.33])

    def test_check_readable(self):
        self.assertIsNone(SqliteDatabase.check_readable())
        with open(self.test_db_path, "wb") as f:
            f.write(b"not a sqlite database" * 100)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(self.test_db_path + suffix):
                os.remove(self.test_db_path + suffix)
        self.assertIsNotNone(SqliteDatabase.check_readable())
        os.remove(self.test_db_path)
        self.assertEqual(SqliteDatabase.check_readable(), "database file not found")


if __name__ == "__main__":
    unittest.main()
