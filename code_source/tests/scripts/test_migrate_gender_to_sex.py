"""scripts/migrate_gender_to_sex.py over an in-memory Firestore (crm_users through a fake RestStore)."""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, Dict, List
from unittest.mock import patch

from support.fake_firestore import FirestoreRepoTestCase

from infrastructure.firestore.competitions import participants
from infrastructure.firestore.competitions import competitions
from infrastructure.firestore.competitions import documents

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts",
                       "migrate_gender_to_sex.py")
_spec = importlib.util.spec_from_file_location("migrate_gender_to_sex", _SCRIPT)
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
                if name in w["fields"]:
                    fields[name] = w["fields"][name]
                else:
                    fields.pop(name, None)


def users_store() -> FakeStore:
    return FakeStore({
        "crm_users": [
            {"id": 1, "last_name": "GRANGER", "gender": "Femme"},
            {"id": 2, "last_name": "WEASLEY", "gender": "Homme"},
            {"id": 3, "last_name": "LOVEGOOD", "gender": "X"},       # not understood
            {"id": 4, "last_name": "POTTER", "gender": ""},          # not given
            {"id": 5, "last_name": "MALFOY", "gender": "Homme", "sex": "F"},  # edited since: sex wins
            {"id": 6, "last_name": "DIGGORY", "sex": "H"},           # already migrated
        ],
        "crm_purchases": [{"id": 30, "user_id": 3, "order_id": 300}],
        "crm_orders": [{"id": 300, "order_ref": "HA-300"}],
    })


class TestMigrateUsers(FirestoreRepoTestCase):

    def run_users(self, store: FakeStore, apply: bool):
        report = migration.Report()
        migration.migrate_users(store, apply, report)
        return report

    def test_dry_run_reports_without_writing(self):
        store = users_store()
        report = self.run_users(store, apply=False)
        self.assertEqual(store.commits, [])
        self.assertEqual(dict(report.users_by_sex), {"F": 2, "H": 1, migration.NOT_GIVEN: 2})
        self.assertEqual(report.users_skipped, 1)
        self.assertEqual(report.unparsed, {3: "HA-300"})  # by id and order, never by name

    def test_apply_sets_sex_and_deletes_gender(self):
        store = users_store()
        self.run_users(store, apply=True)
        users = {d["fields"]["id"]: d["fields"] for d in store.list_all("crm_users")}
        self.assertEqual({uid: u.get("sex") for uid, u in users.items()}, {1: "F", 2: "H", 3: None, 4: None, 5: "F", 6: "H"})
        self.assertFalse(any("gender" in u for u in users.values()))
        write = store.commits[0][0]
        self.assertEqual(write["precondition"], {"updateTime": "t0"})  # never over a concurrent write

    def test_rerun_changes_nothing(self):
        store = users_store()
        self.run_users(store, apply=True)
        report = self.run_users(store, apply=True)
        self.assertEqual((sum(report.users_by_sex.values()), report.users_skipped, len(store.commits)), (0, 6, 1))


class TestMigrateCompetitionsAndDirectory(FirestoreRepoTestCase):

    def setUp(self):
        super().setUp()
        self.seed_adherent(1, gender="Femme")
        self.seed_adherent(2, sex="H")
        participants.add_participant(self.create_competition(), 1)

    def create_competition(self) -> int:
        from domain.competitions.models import Competition
        return competitions.save_competition(Competition(nom="Coupe Rhône"))

    def comp_doc(self) -> Dict[str, Any]:
        return self.fake.list_documents(documents.COLLECTION_COMPETITIONS)[0]

    def add_legacy_copy(self) -> None:
        doc = self.comp_doc()
        doc["participants"][0]["gender"] = "Femme"
        self.fake.upsert_document(documents.COLLECTION_COMPETITIONS, doc["_doc_id"],
                                  {k: v for k, v in doc.items() if not k.startswith("_")})

    def test_dry_run_counts(self):
        self.add_legacy_copy()
        report = migration.Report()
        migration.migrate_competitions(False, report)
        migration.migrate_directory(False, report)
        self.assertEqual((report.competitions, report.participants, report.directory), (1, 1, 1))
        self.assertIn("gender", self.comp_doc()["participants"][0])

    def test_apply(self):
        self.add_legacy_copy()
        stamp = self.comp_doc()["participants"][0]["updated_at"]
        report = migration.Report()
        migration.migrate_competitions(True, report)
        migration.migrate_directory(True, report)
        participant = self.comp_doc()["participants"][0]
        self.assertNotIn("gender", participant)
        self.assertEqual(participant["updated_at"], stamp)  # offline changes queued on this row still apply
        directory = {d["id"]: d for d in self.fake.list_documents(documents.COLLECTION_ADHERENTS)}
        self.assertEqual((directory[1].get("sex"), "gender" in directory[1]), ("F", False))
        self.assertEqual(directory[2]["sex"], "H")


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
        store = users_store()
        with patch.object(migration, "RestStore", return_value=store), patch("builtins.input", return_value="wrong"):
            self.assertEqual(migration.main(["--apply"]), 1)
        self.assertEqual(store.commits, [])
