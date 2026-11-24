"""Tests du cache database.db adossé à Firestore (infrastructure/firestore/cloud_database.py)."""
import copy
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

_test_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src_dir = os.path.join(os.path.dirname(_test_dir), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from infrastructure.firestore.cloud_database import CloudDatabase  # noqa: E402
from infrastructure.firestore.cloud_sync.bootstrap import build_cache, cache_is_valid, create_schema, import_database  # noqa: E402
from infrastructure.firestore.cloud_sync.cache import connect, pending_count, set_state  # noqa: E402
from infrastructure.firestore.client import FirestoreConflictError  # noqa: E402
from infrastructure.firestore.cloud_sync.common import collection_for, ts_key  # noqa: E402
from infrastructure.firestore.cloud_sync.sync import flush, pull  # noqa: E402
from infrastructure.firestore.competitions import member_directory  # noqa: E402
from infrastructure.sqlite.connection import SqliteDatabase  # noqa: E402
from infrastructure.sqlite.email_templates import EmailTemplateRepository  # noqa: E402
from infrastructure.sqlite.members import MemberRepository  # noqa: E402


class FakeStore:
    """Firestore en mémoire : préconditions, horodatages, requêtes par date."""
    project_id = "test-project"

    def __init__(self):
        self.docs = {}  # (collection, id) -> doc
        self.clock = 0
        self.commits = 0
        self.before_commit = None

    def _ts(self):
        self.clock += 1
        return f"2026-10-08T10:{self.clock // 60 % 60:02d}:{self.clock % 60:02d}.{self.clock:06d}Z"

    def _out(self, coll, doc_id):
        d = self.docs[(coll, doc_id)]
        return {"id": doc_id, "fields": copy.deepcopy(d["fields"]), "deleted": d["deleted"],
                "update_time": d["update_time"], "modified_at": d["modified_at"]}

    def list_all(self, coll):
        return [self._out(c, i) for (c, i) in sorted(self.docs) if c == coll]

    def list_modified_since(self, coll, since):
        return [self._out(c, i) for (c, i), d in sorted(self.docs.items())
                if c == coll and ts_key(d["modified_at"]) >= ts_key(since)]

    def get_many(self, coll, ids):
        return {i: (self._out(coll, i) if (coll, i) in self.docs else None) for i in ids}

    def max_int_id(self, coll, field):
        vals = [d["fields"].get(field) for (c, _), d in self.docs.items() if c == coll]
        return max([v for v in vals if isinstance(v, int)] or [0])

    def commit(self, writes):
        if self.before_commit:
            hook, self.before_commit = self.before_commit, None
            hook()
        for w in writes:  # vérification atomique des préconditions
            key = (w["collection"], w["doc_id"])
            pre = w.get("precondition") or {}
            cur = self.docs.get(key)
            if "exists" in pre and bool(cur) != pre["exists"]:
                raise FirestoreConflictError("exists")
            if "updateTime" in pre and (not cur or cur["update_time"] != pre["updateTime"]):
                raise FirestoreConflictError("updateTime")
        self.commits += 1
        out = []
        for w in writes:
            key = (w["collection"], w["doc_id"])
            ts = self._ts()
            if w.get("mask") is None:
                fields = dict(w["fields"])
            else:
                fields = dict(self.docs[key]["fields"]) if key in self.docs else {}
                fields.update({k: w["fields"][k] for k in w["mask"]})
            self.docs[key] = {"fields": fields, "deleted": bool(w.get("deleted")),
                              "update_time": ts, "modified_at": ts}
            out.append({"update_time": ts, "modified_at": ts})
        return out

    # aide aux tests : modification « par un autre poste »
    def remote_patch(self, table, doc_id, **fields):
        key = (collection_for(table), str(doc_id))
        ts = self._ts()
        self.docs[key]["fields"].update(fields)
        self.docs[key].update(update_time=ts, modified_at=ts)


def _seed(path):
    create_schema(path)
    conn = sqlite3.connect(path)
    conn.executescript("""
        DELETE FROM seasons;
        INSERT INTO seasons (id, name, is_active) VALUES (1, '2025-2026', 0), (2, '2026-2027', 1);
        INSERT INTO users (id, last_name, first_name, last_name_key, first_name_key, birth_date, city, phone)
            VALUES (1, 'MARTIN', 'Leo', 'MARTIN', 'LEO', '2010-05-10', 'Jonage', '0600000001'),
                   (2, 'DURAND', 'Zoé', 'DURAND', 'ZOE', '2012-01-02', 'Meyzieu', '0600000002');
        INSERT INTO orders (id, order_ref, order_date, status, season_id) VALUES
            (10, 'A10', '2026-09-01', 'Validated', 2), (11, 'A11', '2025-09-01', 'Validated', 1);
        INSERT INTO purchases (id, order_id, user_id, tarif_name, amount, status) VALUES
            (100, 10, 1, 'Loisir', 150.0, 'Validated'), (101, 10, 2, 'Compétition', 210.5, 'Validated'),
            (102, 11, 1, 'Loisir', 140.0, 'Validated');
        INSERT INTO purchase_options (id, purchase_id, option_name, amount) VALUES (1, 100, 'Assurance Base', 11.0);
        INSERT INTO geocache (address, lat, lon) VALUES ('1 rue de la Paix, 69330, JONAGE, France', 45.79, 5.04);
    """)
    conn.commit()
    conn.close()


def _load(path, season):
    SqliteDatabase.set_db_path(path)
    return MemberRepository.list_flat_member_rows(season)


class CloudDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "source.db")
        _seed(self.src)
        self.store = FakeStore()
        import_database(self.src, self.store)
        self.a = os.path.join(self.tmp, "a.db")
        self.b = os.path.join(self.tmp, "b.db")
        build_cache(self.a, self.store)
        build_cache(self.b, self.store)
        self._saved_path = SqliteDatabase.get_db_path()

    def tearDown(self):
        SqliteDatabase.set_db_path(self._saved_path)

    def sync(self, path):
        conn = connect(path)
        try:
            rep = pull(conn, self.store)
            flush(conn, self.store, "test", rep)
            return rep
        finally:
            conn.close()

    def write(self, path, sql, *params):
        SqliteDatabase.set_db_path(path)
        conn = SqliteDatabase.get_connection()
        conn.execute(sql, params)
        conn.commit()
        conn.close()

    def row(self, path, sql, *params):
        conn = sqlite3.connect(path)
        try:
            return conn.execute(sql, params).fetchone()
        finally:
            conn.close()

    def test_round_trip_identical_view(self):
        for season in ("2025-2026", "2026-2027"):
            self.assertEqual(_load(self.src, season), _load(self.a, season))
        self.assertEqual(len([k for k in self.store.docs if k[0] == "crm_users"]), 2)
        self.assertIn(("crm_purchases", "100"), self.store.docs)
        self.assertIsInstance(self.store.docs[("crm_purchases", "101")]["fields"]["amount"], float)

    def test_local_update_sends_only_changed_fields(self):
        self.write(self.a, "UPDATE users SET city = 'Lyon' WHERE id = 1")
        conn = connect(self.a)
        self.assertEqual(pending_count(conn), 1)
        conn.close()
        rep = self.sync(self.a)
        self.assertEqual(rep.get("pushed"), 1)
        self.assertEqual(self.store.docs[("crm_users", "1")]["fields"]["city"], "Lyon")
        conn = connect(self.a)
        self.assertEqual(pending_count(conn), 0)
        conn.close()
        self.sync(self.b)
        self.assertEqual(self.row(self.b, "SELECT city FROM users WHERE id = 1")[0], "Lyon")

    def test_concurrent_edits_of_different_fields_are_merged(self):
        self.write(self.a, "UPDATE users SET city = 'Lyon' WHERE id = 1")
        self.write(self.b, "UPDATE users SET phone = '0700000000' WHERE id = 1")
        self.sync(self.a)
        self.sync(self.b)  # B : pull fusionne la ville, puis envoie le téléphone
        self.sync(self.a)
        for p in (self.a, self.b):
            self.assertEqual(self.row(p, "SELECT city, phone FROM users WHERE id = 1"), ("Lyon", "0700000000"))
        f = self.store.docs[("crm_users", "1")]["fields"]
        self.assertEqual((f["city"], f["phone"]), ("Lyon", "0700000000"))

    def test_conflict_during_flush_is_retried_with_merge(self):
        self.write(self.a, "UPDATE purchases SET email_sent_date = '2026-10-08' WHERE id = 100")
        # Un autre poste modifie le même document entre la préparation et l'envoi
        self.store.before_commit = lambda: self.store.remote_patch("purchases", 100, is_modified="Oui")
        conn = connect(self.a)
        rep = flush(conn, self.store, "test")
        conn.close()
        self.assertGreaterEqual(rep.get("conflicts", 0), 1)
        f = self.store.docs[("crm_purchases", "100")]["fields"]
        self.assertEqual((f["email_sent_date"], f["is_modified"]), ("2026-10-08", "Oui"))
        self.assertEqual(self.row(self.a, "SELECT is_modified FROM purchases WHERE id = 100")[0], "Oui")

    def test_delete_is_propagated(self):
        self.write(self.a, "DELETE FROM purchase_options WHERE id = 1")
        self.sync(self.a)
        self.assertTrue(self.store.docs[("crm_purchase_options", "1")]["deleted"])
        self.sync(self.b)
        self.assertIsNone(self.row(self.b, "SELECT * FROM purchase_options WHERE id = 1"))
        # une base reconstruite ne contient pas la tombe
        c = os.path.join(self.tmp, "c.db")
        build_cache(c, self.store)
        self.assertIsNone(self.row(c, "SELECT * FROM purchase_options WHERE id = 1"))

    def test_insert_or_replace_logs_replaced_row(self):
        # (order 10, user 2) existe sous l'ID 101 : REPLACE la supprime et crée l'ID 200
        self.write(self.a, "INSERT OR REPLACE INTO purchases (id, order_id, user_id, tarif_name, amount) "
                           "VALUES (200, 10, 2, 'Compétition', 210.5)")
        self.sync(self.a)
        self.assertTrue(self.store.docs[("crm_purchases", "101")]["deleted"])
        self.assertFalse(self.store.docs[("crm_purchases", "200")]["deleted"])
        self.sync(self.b)
        self.assertIsNone(self.row(self.b, "SELECT id FROM purchases WHERE id = 101"))
        self.assertEqual(self.row(self.b, "SELECT user_id FROM purchases WHERE id = 200")[0], 2)

    def test_emergency_contact_syncs_when_created_edited_and_deleted(self):
        self.write(self.a, "INSERT INTO emergency_contacts (id, user_id, name, phone, position) VALUES (1, 1, 'Marie', '0601020304', 0)")
        self.sync(self.a)
        self.assertEqual(self.store.docs[("crm_emergency_contacts", "1")]["fields"]["user_id"], 1)
        self.sync(self.b)
        self.assertEqual(self.row(self.b, "SELECT name, phone, position FROM emergency_contacts WHERE id = 1"), ("Marie", "0601020304", 0))

        self.write(self.b, "UPDATE emergency_contacts SET phone = '0611111111' WHERE id = 1")
        self.sync(self.b)
        self.sync(self.a)
        self.assertEqual(self.row(self.a, "SELECT phone FROM emergency_contacts WHERE id = 1"), ("0611111111",))

        self.write(self.a, "DELETE FROM emergency_contacts WHERE id = 1")
        self.sync(self.a)
        self.assertTrue(self.store.docs[("crm_emergency_contacts", "1")]["deleted"])
        # The tombstone says whose contact it was (the migration skips that member) and nothing about the contact
        self.assertEqual(self.store.docs[("crm_emergency_contacts", "1")]["fields"], {"id": 1, "user_id": 1})
        self.sync(self.b)
        self.assertIsNone(self.row(self.b, "SELECT id FROM emergency_contacts WHERE id = 1"))

    def test_contact_edit_alone_asks_for_a_new_directory(self):
        CloudDatabase._projection_dirty = False
        self.addCleanup(setattr, CloudDatabase, "_projection_dirty", False)
        CloudDatabase._after_sync({"tables": ["emergency_contacts"]})
        self.assertTrue(CloudDatabase._projection_dirty)

    def test_renumbered_member_keeps_their_emergency_contacts(self):
        for path, name in ((self.a, "PETIT"), (self.b, "GRAND")):
            self.write(path, "INSERT INTO users (last_name, first_name, last_name_key, first_name_key) "
                             f"VALUES ('{name}', 'Max', '{name}', 'MAX')")
            self.write(path, "INSERT INTO emergency_contacts (user_id, name, position) "
                             f"SELECT id, 'Contact de {name}', 0 FROM users WHERE last_name = '{name}'")
        self.sync(self.a)
        report = self.sync(self.b)
        self.assertTrue(report.get("renumbered"))
        self.sync(self.a)
        for path in (self.a, self.b):
            pairs =sqlite3.connect(path).execute(
                "SELECT u.last_name, c.name FROM emergency_contacts c JOIN users u ON u.id = c.user_id ORDER BY 1").fetchall()
            self.assertEqual(pairs, [("GRAND", "Contact de GRAND"), ("PETIT", "Contact de PETIT")])

    def test_cache_of_the_previous_format_is_rebuilt(self):
        conn = connect(self.a)
        set_state(conn, "format", "2")
        conn.commit()
        conn.close()
        self.assertFalse(cache_is_valid(self.a, self.store.project_id))

    def test_same_new_id_on_two_posts_is_renumbered(self):
        for p, name in ((self.a, "PETIT"), (self.b, "GRAND")):
            self.write(p, "INSERT INTO users (last_name, first_name, last_name_key, first_name_key) "
                          f"VALUES ('{name}', 'Max', '{name}', 'MAX')")
            self.write(p, "INSERT INTO purchases (order_id, user_id, tarif_name, amount) "
                          f"SELECT 10, id, 'Loisir', 1.0 FROM users WHERE last_name = '{name}'")
        self.sync(self.a)
        rep = self.sync(self.b)
        self.assertTrue(rep.get("renumbered"))
        self.sync(self.a)
        for p in (self.a, self.b):
            ids = dict((n, i) for n, i in sqlite3.connect(p).execute(
                "SELECT last_name, id FROM users WHERE first_name = 'Max'"))
            self.assertEqual(set(ids), {"PETIT", "GRAND"})
            self.assertNotEqual(ids["PETIT"], ids["GRAND"])
            # l'inscription suit son adhérent renuméroté
            got = sqlite3.connect(p).execute(
                "SELECT u.last_name FROM purchases pu JOIN users u ON u.id = pu.user_id "
                "WHERE pu.order_id = 10 AND u.first_name = 'Max' ORDER BY 1").fetchall()
            self.assertEqual([g[0] for g in got], ["GRAND", "PETIT"])

    def test_create_collision_found_by_flush_is_renumbered(self):
        """The remote document appears between this post's last pull and its flush: flush itself renumbers."""
        for p, name in ((self.a, "PETIT"), (self.b, "GRAND")):
            self.write(p, "INSERT INTO users (last_name, first_name, last_name_key, first_name_key) "
                          f"VALUES ('{name}', 'Max', '{name}', 'MAX')")
        self.sync(self.a)
        conn = connect(self.b)
        try:
            rep = flush(conn, self.store, "test")  # no pull first
        finally:
            conn.close()
        self.assertTrue(rep.get("renumbered"))
        petit_id = self.row(self.a, "SELECT id FROM users WHERE last_name = 'PETIT'")[0]
        grand_id = self.row(self.b, "SELECT id FROM users WHERE last_name = 'GRAND'")[0]
        self.assertNotEqual(petit_id, grand_id)
        remote = {d["fields"].get("last_name") for (c, _), d in self.store.docs.items() if c == collection_for("users")}
        self.assertTrue({"PETIT", "GRAND"} <= remote)

    def test_repository_write_path_is_tracked(self):
        SqliteDatabase.set_db_path(self.a)
        EmailTemplateRepository.save_email_template("Bienvenue", "Bienvenue au club", "Bonjour {first_name}")
        self.sync(self.a)
        docs = [d for (c, _), d in self.store.docs.items() if c == "crm_email_templates"]
        self.assertIn("Bienvenue au club", [d["fields"].get("subject") for d in docs])

    def test_pull_does_not_reapply_own_writes(self):
        self.write(self.a, "UPDATE users SET city = 'Lyon' WHERE id = 1")
        self.sync(self.a)
        rep = self.sync(self.a)
        self.assertFalse(rep.get("pulled"))
        self.assertFalse(rep.get("pushed"))


class BrokenStore(FakeStore):
    """Firestore unreachable: every read and write fails."""

    def _fail(self, *args, **kwargs):
        raise ConnectionError("Firestore unreachable")

    list_all = list_modified_since = get_many = commit = _fail


class CloudDatabaseEntryPointsTest(unittest.TestCase):
    """CloudDatabase.sync / flush_only / after_write / ensure_fresh / status / cache_ready over the in-memory store."""

    STATE = ("_store", "_last_report", "_last_error", "_last_sync", "_last_pull", "_projection_dirty")

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        source = os.path.join(self.tmp, "source.db")
        _seed(source)
        self.store = FakeStore()
        import_database(source, self.store)
        self.path = os.path.join(self.tmp, "cache.db")
        build_cache(self.path, self.store)
        saved_path = SqliteDatabase.get_db_path()
        self.addCleanup(SqliteDatabase.set_db_path, saved_path)
        SqliteDatabase.set_db_path(self.path)
        for name in self.STATE:
            self.addCleanup(setattr, CloudDatabase, name, getattr(CloudDatabase, name))
        CloudDatabase._store = self.store
        CloudDatabase._last_error = ""
        CloudDatabase._last_pull = 0.0
        CloudDatabase._projection_dirty = False

    def edit_city(self, city):
        conn = SqliteDatabase.get_connection()
        conn.execute("UPDATE users SET city = ? WHERE id = 1", (city,))
        conn.commit()
        conn.close()

    def pending(self):
        return CloudDatabase.status()["pending"]

    def replication_on(self):
        patcher = mock.patch.dict(os.environ, {"ALJ_CACHE_REPLICATION": "on"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sync_sends_local_edits_and_receives_remote_ones(self):
        self.edit_city("Lyon")
        self.store.remote_patch("users", 2, city="Décines")
        report = CloudDatabase.sync()
        self.assertEqual((report.get("pushed"), report.get("pulled")), (1, 1))
        self.assertEqual(self.store.docs[("crm_users", "1")]["fields"]["city"], "Lyon")
        conn = sqlite3.connect(self.path)
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("SELECT city FROM users WHERE id = 2").fetchone()[0], "Décines")
        self.assertEqual(CloudDatabase.status()["last_error"], "")
        self.assertGreater(CloudDatabase._last_pull, 0)

    def test_full_sync_rebuilds_the_cache(self):
        progress = mock.Mock()
        report = CloudDatabase.sync(full=True, progress=progress)
        self.assertTrue(report["full"])
        self.assertTrue(cache_is_valid(self.path, self.store.project_id))
        self.assertEqual(progress.call_count, 3)

    def test_sync_without_cache_builds_it(self):
        os.remove(self.path)
        self.assertFalse(CloudDatabase.cache_ready())
        self.assertTrue(CloudDatabase.sync()["full"])
        self.assertTrue(CloudDatabase.cache_ready())

    def test_sync_failure_is_reported_not_raised(self):
        CloudDatabase._store = BrokenStore()
        report = CloudDatabase.sync()
        self.assertEqual(report["errors"], ["Firestore unreachable"])
        self.assertEqual(CloudDatabase.status()["last_error"], "Firestore unreachable")

    def test_flush_only_sends_pending_edits(self):
        self.edit_city("Lyon")
        self.assertEqual(self.pending(), 1)
        self.assertEqual(CloudDatabase.flush_only().get("pushed"), 1)
        self.assertEqual(self.pending(), 0)

    def test_flush_only_failure_keeps_the_edit_pending(self):
        self.edit_city("Lyon")
        CloudDatabase._store = BrokenStore()
        self.assertEqual(CloudDatabase.flush_only()["errors"], ["Firestore unreachable"])
        self.assertEqual(self.pending(), 1)

    def test_flush_only_on_invalid_cache_does_nothing(self):
        os.remove(self.path)
        self.assertEqual(CloudDatabase.flush_only(), {})

    def test_after_write_without_replication_sends_nothing(self):
        self.edit_city("Lyon")
        self.assertTrue(CloudDatabase.after_write())
        self.assertEqual(self.pending(), 1)

    def test_after_write_sends_and_rebuilds_the_directory_when_members_changed(self):
        self.replication_on()
        self.edit_city("Lyon")
        with mock.patch.object(member_directory, "rebuild_member_directory", return_value={}) as rebuild:
            self.assertTrue(CloudDatabase.after_write())
        rebuild.assert_called_once()
        self.assertFalse(CloudDatabase._projection_dirty)
        self.assertEqual(self.pending(), 0)

    def test_after_write_reports_a_failed_send(self):
        self.replication_on()
        self.edit_city("Lyon")
        CloudDatabase._store = BrokenStore()
        with mock.patch.object(member_directory, "directory_outdated", return_value=False):
            self.assertFalse(CloudDatabase.after_write())

    def test_directory_stays_dirty_when_its_rebuild_fails(self):
        CloudDatabase._projection_dirty = True
        with mock.patch.object(member_directory, "rebuild_member_directory", side_effect=ConnectionError("down")):
            CloudDatabase.refresh_projection()
        self.assertTrue(CloudDatabase._projection_dirty)

    def test_ensure_fresh_pulls_only_when_stale(self):
        self.replication_on()
        with mock.patch.object(CloudDatabase, "sync") as sync:
            CloudDatabase.ensure_fresh()
            sync.assert_called_once()
            sync.reset_mock()
            CloudDatabase._last_pull = time.time()
            CloudDatabase.ensure_fresh()
            sync.assert_not_called()

    def test_ensure_fresh_without_replication_does_nothing(self):
        with mock.patch.object(CloudDatabase, "sync") as sync:
            CloudDatabase.ensure_fresh()
        sync.assert_not_called()

    def test_cache_ready_is_false_for_a_corrupt_file(self):
        with open(self.path, "wb") as corrupt:
            corrupt.write(b"not a database" * 100)
        self.assertFalse(CloudDatabase.cache_ready())


if __name__ == "__main__":
    unittest.main()
