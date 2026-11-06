"""Member directory (`adherents` collection) on an in-memory Firestore: rebuild from database.db, cached reads, search."""

from unittest.mock import patch

from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.firestore.competitions import documents, member_directory
from infrastructure.sqlite.connection import SqliteDatabase
from support.fake_firestore import FirestoreRepoTestCase
from support.member_db import MemberDbTestCase


class TestSyncAdherentsFromMain(MemberDbTestCase, FirestoreRepoTestCase):
    """`adherents` and `planning` collections rebuilt from the members of database.db."""

    def setUp(self):
        super().setUp()
        self.seed("CMD1", "Jean", "DUPONT", "Compétition - U13/U15", **{"champ_Numéro de Licence FFME (6 chiffres)": "123456"})
        self.seed("CMD2", "Léa", "MARTIN", "Compétition - U13/U15")
        self.seed("CMD3", "Bob", "LOISIR", "Adultes autonomes")
        self.seed_planning("Compétition - U13", ["Compétition - U13/U15"], jour="mercredi", horaires="18h")
        self.seed_planning("Autonome", ["Adultes autonomes"], jour="lundi", horaires="20h")

    def test_sync_writes_directory_and_planning(self):
        report = member_directory.rebuild_member_directory("2026-2027")
        self.assertEqual(report["errors"], [])
        self.assertEqual((report["imported"], report["updated"]), (3, 3))
        self.assertEqual(len(self.fake.store["planning"]), 2)

        adherents = member_directory.list_members()
        self.assertEqual(len(adherents), 3)
        dupont = [a for a in adherents if a["nom"] == "DUPONT"][0]
        self.assertEqual(dupont["num_licence"], "123456")
        self.assertEqual(dupont["tarif"], "Compétition - U13/U15")
        self.assertEqual(dupont["creneau_groupe"], "Compétition - U13")

        self.assertEqual(dupont["statut"], "Validé")  # "Validated" normalized

        # Idempotent: a second sync rewrites the same documents
        member_directory.rebuild_member_directory("2026-2027")
        self.assertEqual(len(member_directory.adherents_raw()), 3)

    def test_sync_copies_the_first_emergency_contact(self):
        conn = SqliteDatabase.get_connection()
        try:
            conn.execute("INSERT INTO emergency_contacts (user_id, name, phone, position) "
                         "SELECT id, 'Deuxième', '0622222222', 1 FROM users WHERE last_name = 'DUPONT'")
            conn.execute("INSERT INTO emergency_contacts (user_id, name, phone, position) "
                         "SELECT id, 'Principal', '0611111111', 0 FROM users WHERE last_name = 'DUPONT'")
            conn.commit()
        finally:
            conn.close()
        member_directory.rebuild_member_directory("2026-2027")
        dupont = [a for a in member_directory.list_members() if a["nom"] == "DUPONT"][0]
        self.assertEqual((dupont["emergency_name"], dupont["emergency_phone"]), ("Principal", "0611111111"))

    def test_sync_keeps_the_highest_priority_purchase(self):
        """Two purchases of the season (two orders): the confirmed licence wins over a later cancelled one,
        and the tariff comes from the same purchase."""
        conn = SqliteDatabase.get_connection()
        try:
            # The importer refuses a lower-priority purchase: the cancelled one is written directly, after the other
            conn.execute("UPDATE purchases SET status = 'Terminé' WHERE tarif_name = 'Compétition - U13/U15'")
            conn.execute("INSERT INTO orders (order_ref, season_id) SELECT 'CMD4', season_id FROM orders WHERE order_ref = 'CMD1'")
            conn.execute("INSERT INTO purchases (order_id, user_id, tarif_name, amount, status) "
                         "SELECT (SELECT id FROM orders WHERE order_ref = 'CMD4'), user_id, 'Adultes autonomes', 150, 'Annulé' "
                         "FROM purchases WHERE tarif_name = 'Compétition - U13/U15' AND order_id = "
                         "(SELECT id FROM orders WHERE order_ref = 'CMD1')")
            conn.commit()
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM v_member_flat WHERE last_name = 'DUPONT'").fetchone()[0], 2)
        finally:
            conn.close()
        report = member_directory.rebuild_member_directory("2026-2027")
        self.assertEqual((report["errors"], report["imported"]), ([], 3))
        dupont = [a for a in member_directory.list_members() if a["nom"] == "DUPONT"][0]
        self.assertEqual((dupont["statut"], dupont["tarif"], dupont["creneau_groupe"]),
                         ("Terminé", "Compétition - U13/U15", "Compétition - U13"))
        self.assertEqual([a["nom"] for a in member_directory.list_members(statuses=["Terminé"])], ["DUPONT", "MARTIN"])



class TestAdherents(FirestoreRepoTestCase):
    def test_listing_and_search(self):
        self.seed_adherent(101, licence="654321")
        self.seed_adherent(102, nom="DUPONT", prenom="Léa", licence="111222", tarif="Loisir")
        adhs = member_directory.list_members()
        self.assertEqual(len(adhs), 2)
        by_id = {a["id"]: a for a in adhs}
        self.assertEqual(by_id[101]["num_licence"], "654321")

        self.assertEqual(len(member_directory.list_members(search="dupont")), 1)
        self.assertEqual(len(member_directory.list_members(competition_only=True)), 1)
        self.assertEqual(len(member_directory.adherents_raw()), 2)

    def test_status_filter(self):
        self.seed_adherent(101)
        self.seed_adherent(102, nom="DUPONT", statut="Validé")
        self.seed_adherent(103, nom="PETIT", statut="termine")  # normalized
        ids = lambda **kw: sorted(a["id"] for a in member_directory.list_members(**kw))  # noqa: E731
        self.assertEqual(ids(), [101, 102, 103])
        self.assertEqual(ids(statuses=["Terminé"]), [101, 103])
        self.assertEqual(ids(statuses=["Terminé", "Validé"]), [101, 102, 103])
        self.assertEqual(ids(statuses=[]), [])

    def test_directory_without_status_is_rewritten_after_next_write(self):
        """A directory written before `statut` existed reports itself outdated: CloudDatabase.refresh_projection, run
        after the next replicated write, rewrites it."""
        self.seed_adherent(101)
        with patch.object(CloudDatabase, "_projection_dirty", False), patch.object(member_directory._state, "heal_requested", False), \
                patch.object(member_directory._state, "outdated", False), \
                patch.object(member_directory, "rebuild_member_directory", return_value={"errors": []}) as rewrite:
            member_directory.list_members()
            CloudDatabase.refresh_projection()
            rewrite.assert_not_called()
            self.fake.upsert_document(documents.COLLECTION_ADHERENTS, "102", {"id": 102, "nom": "ANCIEN"})
            member_directory.invalidate_cache()
            self.assertEqual(member_directory.list_members(statuses=["Terminé"])[0]["id"], 101)  # strict until rewritten
            self.assertTrue(member_directory.directory_outdated())
            CloudDatabase.refresh_projection()
            rewrite.assert_called_once()
            # Still lacking after the rewrite (a member no longer synced): not sent for rewriting again
            member_directory._state.outdated = False
            member_directory.invalidate_cache()
            member_directory.list_members()
            self.assertFalse(member_directory.directory_outdated())
