"""Firestore access store: the three collections, through FirestoreClient (in-memory stand-in)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from infrastructure.firestore import access_store
from infrastructure.firestore.access_store import FirestoreAccessStore
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from support.fake_access import role_entry
from support.fake_firestore import use_fake_firestore


class TestFirestoreAccessStore(unittest.TestCase):

    def setUp(self):
        self.fake = use_fake_firestore(self)
        self.store = FirestoreAccessStore()

    def test_roles_by_email(self):
        self.assertTrue(self.store.create_role(role_entry("a@alj.example", "coach", "A")))
        self.assertFalse(self.store.create_role(role_entry("a@alj.example", "admin")))  # never overwritten
        self.assertEqual(self.fake.store[access_store.ROLES_COLLECTION]["a@alj.example"]["role"], "coach")
        self.store.update_role("a@alj.example", {"last_sign_in_at": "2026-10-30T09:00:00+00:00"})
        entry = self.store.get_role("a@alj.example")
        self.assertEqual((entry["role"], entry["display_name"], entry["last_sign_in_at"]),
                         ("coach", "A", "2026-10-30T09:00:00+00:00"))
        self.assertEqual([e["email"] for e in self.store.list_roles()], ["a@alj.example"])
        self.store.delete_role("a@alj.example")
        self.assertIsNone(self.store.get_role("a@alj.example"))

    def test_requests_and_history(self):
        self.store.save_request({"email": "d@alj.example", "google_display_name": "D", "first_requested_at": "t1",
                                 "last_requested_at": "t2", "dismissed_at": None})
        self.assertEqual(self.store.get_request("d@alj.example")["last_requested_at"], "t2")
        self.store.delete_request("d@alj.example")
        self.assertEqual(self.store.list_requests(), [])
        for _ in range(2):  # same second: two entries
            self.store.add_history({"at": "2026-10-30T09:00:00+00:00", "author": "bootstrap", "action": "bootstrap",
                                    "target_email": "a@alj.example", "old_role": None, "new_role": "admin"})
        self.assertEqual(len(self.store.list_history()), 2)


class TestCreateDocument(unittest.TestCase):
    """REST create-if-absent: POST with documentId, 409 ALREADY_EXISTS when the id is taken."""

    def _post(self, status):
        resp = MagicMock(status_code=status, text="")
        with patch.object(FirestoreClient, "get_access_token", return_value="t"), \
             patch("infrastructure.firestore.client.requests.post", return_value=resp) as post:
            result = FirestoreClient.create_document("access_roles", "a@alj.example", {"role": "admin"})
        return result, post

    def test_created(self):
        result, post = self._post(200)
        self.assertTrue(result)
        self.assertTrue(post.call_args.args[0].endswith("/access_roles"))
        self.assertEqual(post.call_args.kwargs["params"], {"documentId": "a@alj.example"})

    def test_already_exists(self):
        self.assertFalse(self._post(409)[0])

    def test_other_error(self):
        with self.assertRaises(FirestoreError):
            self._post(500)
