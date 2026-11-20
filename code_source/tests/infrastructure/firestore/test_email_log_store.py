"""Firestore e-mail log: entries written once, a competition's found with array-contains."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from domain.email_log import EmailLogEntry, LoggedRecipient
from infrastructure.firestore import email_log
from infrastructure.firestore.client import FirestoreClient
from infrastructure.firestore.email_log import FirestoreEmailLogStore
from support.fake_firestore import use_fake_firestore


def sent_entry(at: str, competition_ids: list[int]) -> EmailLogEntry:
    return EmailLogEntry(at=at, author="coach@alj.example", kind="competition_email", template="Relance", subject="Rappel",
                         competition_ids=competition_ids, member_ids=[3],
                         recipients=[LoggedRecipient(member_id=3, email="a@example.org", name="Ana B", status="sent", error=None)])


class TestFirestoreEmailLogStore(unittest.TestCase):

    def setUp(self):
        self.fake = use_fake_firestore(self)
        self.store = FirestoreEmailLogStore()

    def test_write_and_read_a_competition(self):
        for at, ids in (("2026-11-01T09:00:00+00:00", [7]), ("2026-11-01T09:00:00+00:00", [7, 8]), ("2026-11-02T09:00:00+00:00", [8])):
            self.store.add_entry(sent_entry(at, ids))  # same second: two documents
        self.assertEqual(len(self.fake.store[email_log.COLLECTION]), 3)
        entries = self.store.list_for_competition(7)
        self.assertEqual(sorted(e["competition_ids"] for e in entries), [[7], [7, 8]])
        self.assertEqual(entries[0]["recipients"], sent_entry("", [7])["recipients"])
        self.assertEqual((entries[0]["template"], entries[0]["member_ids"]), ("Relance", [3]))

    def test_latest_of_the_whole_log_newest_first(self):
        for at, ids in (("2026-11-01T09:00:00+00:00", [7]), ("2026-11-03T09:00:00+00:00", []), ("2026-11-02T09:00:00+00:00", [8])):
            self.store.add_entry(sent_entry(at, ids))
        self.fake.upsert_document(email_log.COLLECTION, "x", {"kind": "fax", "at": "2026-11-04T09:00:00+00:00"})
        self.assertEqual([e["at"][:10] for e in self.store.list_latest(3)], ["2026-11-03", "2026-11-02"])

    def test_unknown_kind_left_out(self):
        self.fake.upsert_document(email_log.COLLECTION, "x", {"kind": "fax", "competition_ids": [7]})
        self.assertEqual(self.store.list_for_competition(7), [])


class TestListContaining(unittest.TestCase):

    def test_query(self):
        resp = MagicMock(status_code=200, text="")
        resp.json.return_value = [{"document": {"name": "projects/p/databases/(default)/documents/email_log/e1",
                                                "fields": {"competition_ids": {"arrayValue": {"values": [{"integerValue": "7"}]}}}}}]
        with patch.object(FirestoreClient, "get_access_token", return_value="t"), \
             patch("infrastructure.firestore.client.requests.post", return_value=resp) as post:
            docs = FirestoreClient.list_containing("email_log", "competition_ids", 7)
        query = post.call_args.kwargs["json"]["structuredQuery"]
        self.assertEqual(query["where"], {"fieldFilter": {"field": {"fieldPath": "competition_ids"}, "op": "ARRAY_CONTAINS",
                                                          "value": {"integerValue": "7"}}})
        self.assertNotIn("orderBy", query)  # no composite index needed
        self.assertEqual([(d["_doc_id"], d["competition_ids"]) for d in docs], [("e1", [7])])
