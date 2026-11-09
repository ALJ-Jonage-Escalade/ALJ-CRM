"""FirestoreAccessStore: stored documents read as typed entries; unknown roles and actions are left out."""

from __future__ import annotations

from unittest.mock import patch

from infrastructure.firestore.access_store import FirestoreAccessStore

CLIENT = "infrastructure.firestore.access_store.FirestoreClient"


def test_list_roles_leaves_out_an_unknown_role() -> None:
    docs = [{"_doc_id": "albus@hogwarts.example", "role": "admin"}, {"_doc_id": "peeves@hogwarts.example", "role": "Admin"}]
    with patch(f"{CLIENT}.list_documents", return_value=docs):
        entries = FirestoreAccessStore().list_roles()
    assert [(entry["email"], entry["role"]) for entry in entries] == [("albus@hogwarts.example", "admin")]


def test_get_role_of_an_unknown_role_is_none() -> None:
    with patch(f"{CLIENT}.get_document", return_value={"_doc_id": "peeves@hogwarts.example", "role": "poltergeist"}):
        assert FirestoreAccessStore().get_role("peeves@hogwarts.example") is None


def test_list_history_leaves_out_an_unknown_action() -> None:
    docs = [{"at": "2026-11-08T10:00:00", "action": "removed", "target_email": "a@x.example"}, {"action": "teleported"}]
    with patch(f"{CLIENT}.list_latest", return_value=docs):
        entries = FirestoreAccessStore().list_history(10)
    assert [entry["action"] for entry in entries] == ["removed"]
