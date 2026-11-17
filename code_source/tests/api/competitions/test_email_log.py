"""GET /api/competitions/{id}/email-log: the history and contact summary, open to readonly."""

from support.api_case import ApiTestCase

from infrastructure.firestore.competitions import participants
from infrastructure.security.api_auth import required_role
from infrastructure.security.roles import Role
from services.communications.email_log import logged_recipient, record_send


class TestCompetitionEmailLog(ApiTestCase):

    def test_history_and_summary(self):
        self.seed_adherent(3, email="ana@example.org")
        comp = self.create()["id"]
        participants.add_participant(comp, 3)
        record_send("competition_email", "coach@alj.example", [logged_recipient("ana@example.org", "Ana", 3)], "Rappel",
                    competition_ids=[comp])
        record_send("competition_all_paid", "system", [logged_recipient("club@alj.example")], "Tous payés", competition_ids=[comp])

        r = self.client.get(f"/api/competitions/{comp}/email-log")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        by_kind = {e["kind"]: e for e in body["entries"]}
        self.assertEqual(set(by_kind), {"competition_all_paid", "competition_email"})
        sent_at = by_kind["competition_email"]["at"]
        self.assertEqual(body["summary"]["last_competitor_email_at"], sent_at)
        self.assertEqual(body["summary"]["competitors"],
                         [{"member_id": 3, "email": "ana@example.org", "last_sent_at": sent_at, "last_failed": False}])

    def test_unknown_competition(self):
        self.assertEqual(self.client.get("/api/competitions/999/email-log").status_code, 404)

    def test_readonly_reads_it(self):
        self.assertEqual(required_role("GET", "/api/competitions/7/email-log"), Role.READONLY)
