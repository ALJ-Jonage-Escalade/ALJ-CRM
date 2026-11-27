"""scripts/migrate_ffme_category.py over an in-memory Firestore (crm_* through a fake RestStore). Deleted with the
script once it has run in production (plans/ffme-categories.md D10)."""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, Dict, List
from unittest.mock import patch

from support.fake_firestore import FirestoreRepoTestCase

from domain.competitions.models import Competition
from infrastructure.firestore.competitions import competitions, documents, participants

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts",
                       "migrate_ffme_category.py")
_spec = importlib.util.spec_from_file_location("migrate_ffme_category", _SCRIPT)
assert _spec and _spec.loader
migration = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = migration  # its dataclasses look their module up
_spec.loader.exec_module(migration)


class FakeStore:
    """The RestStore calls of the script: documents as RestStore parses them, commits applied with their mask."""
    project_id = "demo-alj"

    def __init__(self, collections: Dict[str, List[Dict[str, Any]]]):
        self.docs = {name: {str(i): {"id": str(i), "fields": dict(fields), "deleted": False, "update_time": "t0"}
                            for i, fields in enumerate(rows)} for name, rows in collections.items()}
        self.commits: List[List[Dict[str, Any]]] = []

    def list_all(self, collection: str) -> List[Dict[str, Any]]:
        return [dict(d, fields=dict(d["fields"])) for d in self.docs.get(collection, {}).values()]

    def commit(self, writes: List[Dict[str, Any]]) -> None:
        self.commits.append(writes)
        for w in writes:
            fields = self.docs[w["collection"]][w["doc_id"]]["fields"]
            for name in w["mask"]:
                fields[name] = w["fields"][name]


def members_store() -> FakeStore:
    """GRANGER renewed for 2026-2027 (born 2014: U15); WEASLEY only 2025-2026 (born 2016: U11 that season);
    POTTER without birth date; MALFOY edited since (category kept); LOVEGOOD without membership."""
    return FakeStore({
        "crm_seasons": [{"id": 1, "name": "2025-2026"}, {"id": 2, "name": "2026-2027"}],
        "crm_orders": [{"id": 10, "season_id": 1}, {"id": 11, "season_id": 2}, {"id": 12, "season_id": 1},
                       {"id": 13, "season_id": 2}, {"id": 14, "season_id": 2}],
        "crm_purchases": [{"id": 20, "user_id": 1, "order_id": 10}, {"id": 21, "user_id": 1, "order_id": 11},
                          {"id": 22, "user_id": 2, "order_id": 12}, {"id": 23, "user_id": 3, "order_id": 13},
                          {"id": 24, "user_id": 4, "order_id": 14}],
        "crm_users": [
            {"id": 1, "last_name": "GRANGER", "birth_date": "2014-09-19"},
            {"id": 2, "last_name": "WEASLEY", "birth_date": "2016-03-01"},
            {"id": 3, "last_name": "POTTER", "birth_date": ""},
            {"id": 4, "last_name": "MALFOY", "birth_date": "1980-06-05", "ffme_category": "SENIOR"},
            {"id": 5, "last_name": "LOVEGOOD", "birth_date": "2014-02-13"},
        ],
    })


def categories(store: FakeStore) -> Dict[Any, Any]:  # Any: Firestore values
    return {d["fields"]["id"]: d["fields"].get("ffme_category") for d in store.list_all("crm_users")}


class TestMigrateUsers(FirestoreRepoTestCase):

    def run_users(self, store: FakeStore, apply: bool):
        report = migration.Report()
        migration.migrate_users(store, apply, report)
        return report

    def test_dry_run_reports_without_writing(self):
        store = members_store()
        report = self.run_users(store, apply=False)
        self.assertEqual(store.commits, [])
        self.assertEqual(dict(report.users_by_category), {"U15": 1, "U11": 1, migration.NONE: 2})
        self.assertEqual(report.users_skipped, 1)
        self.assertEqual(report.not_computed, [3, 5])  # by id, never by name

    def test_apply_sets_the_category_of_each_member_s_latest_season(self):
        store = members_store()
        self.run_users(store, apply=True)
        self.assertEqual(categories(store), {1: "U15", 2: "U11", 3: "", 4: "SENIOR", 5: ""})
        self.assertEqual(store.commits[0][0]["precondition"], {"updateTime": "t0"})  # never over a concurrent write

    def test_rerun_changes_nothing(self):
        store = members_store()
        self.run_users(store, apply=True)
        report = self.run_users(store, apply=True)
        self.assertEqual((sum(report.users_by_category.values()), report.users_skipped, len(store.commits)), (0, 5, 1))


class TestMigrateCompetitionsAndDirectory(FirestoreRepoTestCase):
    """GRANGER (born 2014) in a competition of March 2026 (season 2025-2026: U13) and of October 2026 (U15)."""

    def setUp(self):
        super().setUp()
        self.seed_adherent(1, nom="GRANGER")
        self.seed_adherent(2, nom="WEASLEY", ffme_category="U11")
        self.store = members_store()
        for number, (name, day) in enumerate((("Coupe de printemps", "2026-03-14"), ("Open d'automne", "2026-10-03"), ("Sans date", ""))):
            competition_id = competitions.save_competition(Competition(id=700 + number, nom=name, date_competition=day))
            participants.add_participant(competition_id, 1)
            self.strip_category(competition_id, legacy="U13Femme")

    def strip_category(self, competition_id: int, legacy: str) -> None:
        """A participant row as written before the change: no `categorie`, the MyCompet `categorie_ffme`."""
        doc = documents.load_comp_doc(competition_id)
        assert doc
        rows = [{**{k: v for k, v in row.items() if k != "categorie"}, "categorie_ffme": legacy} for row in doc["participants"]]
        self.fake.upsert_document(documents.COLLECTION_COMPETITIONS, doc["_doc_id"], {
            **{k: v for k, v in doc.items() if not k.startswith("_")}, "participants": rows})

    def rows_by_name(self) -> Dict[str, Dict[str, Any]]:
        return {d["nom"]: d["participants"][0] for d in self.fake.list_documents(documents.COLLECTION_COMPETITIONS)}

    def test_dry_run_counts(self):
        report = migration.Report()
        migration.migrate_competitions(self.store, False, report)
        migration.migrate_directory(self.store, False, report)
        self.assertEqual((report.competitions, report.participants, report.directory), (3, 3, 1))
        self.assertNotIn("categorie", self.rows_by_name()["Open d'automne"])

    def test_apply_computes_the_category_of_the_competition_s_season(self):
        stamp = self.rows_by_name()["Open d'automne"]["updated_at"]
        report = migration.Report()
        migration.migrate_competitions(self.store, True, report)
        migration.migrate_directory(self.store, True, report)
        rows = self.rows_by_name()
        self.assertEqual({name: row["categorie"] for name, row in rows.items()},
                         {"Coupe de printemps": "U13", "Open d'automne": "U15", "Sans date": ""})
        self.assertFalse(any("categorie_ffme" in row for row in rows.values()))
        self.assertEqual(rows["Open d'automne"]["updated_at"], stamp)  # offline changes queued on this row still apply
        directory = {d["id"]: d for d in self.fake.list_documents(documents.COLLECTION_ADHERENTS)}
        self.assertEqual((directory[1]["ffme_category"], directory[2]["ffme_category"]), ("U15", "U11"))

    def test_rerun_changes_nothing(self):
        migration.migrate_competitions(self.store, True, migration.Report())
        migration.migrate_directory(self.store, True, migration.Report())
        report = migration.Report()
        migration.migrate_competitions(self.store, True, report)
        migration.migrate_directory(self.store, True, report)
        self.assertEqual((report.competitions, report.participants, report.directory), (0, 0, 0))


class TestTargetGuards(FirestoreRepoTestCase):

    def test_emulator_needs_the_flag(self):
        with patch.dict(os.environ, {"ALJ_ENV": "dev", "FIRESTORE_EMULATOR_HOST": "localhost:8086"}):
            self.assertEqual(migration.main([]), 2)

    def test_emulator_host_outside_dev_mode_is_refused(self):
        # runtime_env ignores the emulator outside dev mode: the script would otherwise reach production
        with patch.dict(os.environ, {"FIRESTORE_EMULATOR_HOST": "localhost:8086"}):
            self.assertEqual(migration.main(["--emulator"]), 2)
            self.assertEqual(migration.main([]), 2)

    def test_production_apply_needs_the_project_id_typed(self):
        store = members_store()
        with patch.object(migration, "RestStore", return_value=store), patch("builtins.input", return_value="wrong"):
            self.assertEqual(migration.main(["--apply"]), 1)
        self.assertEqual(store.commits, [])
