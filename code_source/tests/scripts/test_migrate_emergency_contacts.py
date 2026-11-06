"""scripts/migrate_emergency_contacts.py over an in-memory Firestore (plans/emergency-contacts.md, phase 7)."""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from infrastructure.firestore.client import FirestoreConflictError

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts",
                       "migrate_emergency_contacts.py")
_spec = importlib.util.spec_from_file_location("migrate_emergency_contacts", _SCRIPT)
assert _spec and _spec.loader
migration = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = migration  # its dataclasses look their module up
_spec.loader.exec_module(migration)

USERS = "crm_users"
CONTACTS = "crm_emergency_contacts"


class FakeStore:
    """The RestStore calls of the script, with the "must not exist" precondition checked."""
    project_id = "demo-alj"

    def __init__(self, users: List[Dict[str, Any]], contacts: Optional[List[Dict[str, Any]]] = None, purchases: Optional[List[Dict[str, Any]]] = None):
        self.docs: Dict[str, Dict[str, Dict[str, Any]]] = {USERS: {}, CONTACTS: {}, "crm_purchases": {}, "crm_orders": {}}
        for user in users:
            self.docs[USERS][str(user["id"])] = {"id": str(user["id"]), "fields": dict(user), "deleted": False}
        for contact in contacts or []:
            deleted = bool(contact.pop("_deleted", False))
            self.docs[CONTACTS][str(contact["id"])] = {"id": str(contact["id"]), "fields": dict(contact), "deleted": deleted}
        for purchase in purchases or []:
            self.docs["crm_purchases"][str(purchase["id"])] = {"id": str(purchase["id"]), "fields": dict(purchase), "deleted": False}
            ref = {"id": purchase["order_id"], "order_ref": f"HA-{purchase['order_id']}"}
            self.docs["crm_orders"][str(purchase["order_id"])] = {"id": str(purchase["order_id"]), "fields": ref, "deleted": False}
        self.commits: List[List[Dict[str, Any]]] = []
        self.before_commit: List[Any] = []

    def list_all(self, collection: str) -> List[Dict[str, Any]]:
        return [dict(d, fields=dict(d["fields"])) for d in self.docs.get(collection, {}).values()]

    def max_int_id(self, collection: str, field: str) -> int:
        return max((d["fields"].get(field, 0) for d in self.docs.get(collection, {}).values()), default=0)

    def commit(self, writes: List[Dict[str, Any]]) -> None:
        if self.before_commit:
            self.before_commit.pop(0)()
        for write in writes:
            if write["precondition"] == {"exists": False} and write["doc_id"] in self.docs[write["collection"]]:
                raise FirestoreConflictError("exists")
        self.commits.append(writes)
        for write in writes:
            self.docs[write["collection"]][write["doc_id"]] = {"id": write["doc_id"], "fields": dict(write["fields"]), "deleted": write["deleted"]}

    def contacts_of(self, user_id: int) -> List[tuple]:
        rows = [d["fields"] for d in self.docs[CONTACTS].values() if not d["deleted"] and d["fields"].get("user_id") == user_id]
        return [(r["name"], r["phone"], r["position"]) for r in sorted(rows, key=lambda r: r["position"])]


def user(user_id: int, name1: Any = "", phone1: Any = "", name2: Any = "", phone2: Any = "") -> Dict[str, Any]:
    return {"id": user_id, "last_name": "SECRET", "emergency1_name": name1, "emergency1_phone": phone1, "emergency2_name": name2, "emergency2_phone": phone2}


def run(store: FakeStore, apply: bool = True):
    report = migration.Report()
    migration.migrate(store, apply, report)
    return report


def test_copies_both_contacts_in_order() -> None:
    store = FakeStore([user(1, "Marie", "0601020304", "Paul", "0605060708")])
    report = run(store)
    assert store.contacts_of(1) == [("Marie", "0601020304", 0), ("Paul", "0605060708", 1)]
    assert report.by_count[2] == 1
    write = store.commits[0][0]
    assert write["precondition"] == {"exists": False}
    assert write["mask"] is None and write["deleted"] is False
    assert write["by"]  # sets _modified_at and _modified_by through RestStore.commit, so instances pull it


def test_dry_run_writes_nothing() -> None:
    store = FakeStore([user(1, "Marie", "0601020304")])
    report = run(store, apply=False)
    assert store.commits == []
    assert report.by_count[1] == 1


def test_ids_continue_after_the_highest_including_tombstones() -> None:
    store = FakeStore([user(1, "Marie", "01")], [{"id": 7, "user_id": 2, "_deleted": True}])
    run(store)
    assert "8" in store.docs[CONTACTS]


def test_rerun_changes_nothing() -> None:
    store = FakeStore([user(1, "Marie", "0601020304")])
    run(store)
    commits = len(store.commits)
    report = run(store)
    assert len(store.commits) == commits
    assert report.skipped == 1


def test_member_whose_contacts_were_removed_is_not_restored() -> None:
    store = FakeStore([user(1, "Marie", "0601020304")], [{"id": 3, "user_id": 1, "_deleted": True}])
    report = run(store)
    assert store.contacts_of(1) == []
    assert report.skipped == 1


def test_never_writes_to_the_users() -> None:
    store = FakeStore([user(1, "Marie", "01")])
    run(store)
    assert {write["collection"] for commit in store.commits for write in commit} == {CONTACTS}


def test_drops_the_same_person_twice_and_blank_rows() -> None:
    store = FakeStore([user(1, "Marie", "06 01 02 03 04", "Marie D.", "+33601020304"), user(2, None, None, " ", ""), {"id": 3, "last_name": "SANS"}])
    report = run(store)
    assert store.contacts_of(1) == [("Marie", "06 01 02 03 04", 0)]
    assert store.contacts_of(2) == []
    assert report.duplicates == 1
    assert (report.by_count[0], report.by_count[1]) == (2, 1)


def test_reports_a_member_whose_export_changes_by_id_and_order_never_by_name() -> None:
    store = FakeStore([user(1, "", "", "Paul", "0605060708")], purchases=[{"id": 9, "user_id": 1, "order_id": 90}])
    report = run(store)
    assert store.contacts_of(1) == [("Paul", "0605060708", 0)]
    assert report.first_contact_blank == {1: "HA-90"}


def test_reports_rows_that_differ_from_the_old_columns() -> None:
    store = FakeStore(
        [user(1, "Marie", "01"), user(2, "Paul", "02")],
        [{"id": 1, "user_id": 1, "name": "Marie Dupont", "phone": "01", "position": 0}, {"id": 2, "user_id": 2, "name": "Paul", "phone": "02", "position": 0}],
    )
    report = run(store, apply=False)
    assert set(report.different) == {1}


def test_prints_no_name_and_no_phone(capsys: pytest.CaptureFixture[str]) -> None:
    store = FakeStore([user(1, "", "", "Paul", "0605060708")], [{"id": 1, "user_id": 2, "name": "Anna", "phone": "0611111111", "position": 0}])
    store.docs[USERS]["2"] = {"id": "2", "fields": user(2, "Marie", "0622222222"), "deleted": False}
    migration.print_report(run(store), True)
    output = capsys.readouterr().out
    for private in ("Paul", "0605060708", "Anna", "0611111111", "Marie", "0622222222", "SECRET"):
        assert private not in output


def test_id_taken_by_an_instance_is_retried_on_a_new_id() -> None:
    store = FakeStore([user(1, "Marie", "01")])
    taken = {"id": "1", "fields": {"id": 1, "user_id": 2, "name": "Autre", "phone": "09", "position": 0}, "deleted": False}
    store.before_commit = [lambda: store.docs[CONTACTS].__setitem__("1", taken)]
    run(store)
    assert store.contacts_of(1) == [("Marie", "01", 0)]
    assert store.docs[CONTACTS]["1"] == taken
    assert "2" in store.docs[CONTACTS]


def test_gives_up_after_repeated_conflicts() -> None:
    store = FakeStore([user(1, "Marie", "01")])

    def always_conflict(_writes: List[Dict[str, Any]]) -> None:
        raise FirestoreConflictError("exists")

    with patch.object(store, "commit", always_conflict), pytest.raises(SystemExit):
        run(store)


def test_emulator_needs_the_flag() -> None:
    with patch.dict(os.environ, {"ALJ_ENV": "dev", "FIRESTORE_EMULATOR_HOST": "localhost:8086"}):
        assert migration.main([]) == 2


def test_emulator_host_outside_dev_mode_is_refused() -> None:
    with patch.dict(os.environ, {"FIRESTORE_EMULATOR_HOST": "localhost:8086"}):
        assert migration.main(["--emulator"]) == 2


def test_production_apply_needs_the_project_id_typed() -> None:
    store = FakeStore([user(1, "Marie", "01")])
    with patch.object(migration, "RestStore", return_value=store), patch("builtins.input", return_value="wrong"):
        assert migration.main(["--apply"]) == 1
    assert store.commits == []
