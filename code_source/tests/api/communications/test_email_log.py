"""GET /api/admin/email-log: the latest sends of the whole app, for Communications › Historique des envois (admin)."""

from __future__ import annotations

from unittest.mock import patch

from support.api_case import ApiTestCase

from domain.communications.email_log import EmailKind, EmailLogEntry
from services.communications import email_log
from services.communications.email_log import logged_recipient


def entry(at: str, kind: EmailKind, competition_ids: list[int] | None = None) -> EmailLogEntry:
    return EmailLogEntry(at=at, author="coach@alj.example", kind=kind, template="", subject="Rappel",
                         competition_ids=competition_ids or [], member_ids=[3],
                         recipients=[logged_recipient("ana@example.org", "Ana", 3)])


class TestGlobalEmailLog(ApiTestCase):

    def test_latest_sends_newest_first_with_competition_names(self):
        comp = self.create(nom="Coupe Rhône")["id"]
        store = email_log.current_store()
        store.add_entry(entry("2026-11-01T09:00:00+00:00", "attestation"))
        store.add_entry(entry("2026-11-02T09:00:00+00:00", "competition_email", [comp]))

        r = self.client.get("/api/admin/email-log")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual([e["kind"] for e in body["entries"]], ["competition_email", "attestation"])
        self.assertEqual(body["competition_names"], {str(comp): "Coupe Rhône"})
        self.assertFalse(body["truncated"])

    def test_cap_reached_lists_the_newest_only(self):
        store = email_log.current_store()
        for day in (1, 2, 3):
            store.add_entry(entry(f"2026-11-0{day}T09:00:00+00:00", "member_email"))
        with patch.object(email_log, "RECENT_LIMIT", 2):
            body = self.client.get("/api/admin/email-log").json()
        self.assertEqual([e["at"][:10] for e in body["entries"]], ["2026-11-03", "2026-11-02"])
        self.assertTrue(body["truncated"])

    def test_deleted_competition_has_no_name(self):
        email_log.current_store().add_entry(entry("2026-11-01T09:00:00+00:00", "results_batch", [999]))
        body = self.client.get("/api/admin/email-log").json()
        self.assertEqual(body["entries"][0]["competition_ids"], [999])
        self.assertEqual(body["competition_names"], {})
