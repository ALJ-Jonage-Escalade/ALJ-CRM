"""Participant flag changes queued on a phone while offline (plan phase 5b), sent later with
`unchanged_since`: the participant's `updated_at` the phone saw. One test per situation of
the plan's conflict table (K1-K9)."""

import datetime
from types import SimpleNamespace
from unittest.mock import patch

from support.api_case import ApiTestCase

from domain.competitions.models import PAIEMENT_PAYE
from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo


class TestQueuedFlagChanges(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.seed_adherent(1)
        self.comp = self.create()["id"]
        Repo.add_participant(self.comp, 1, selectionne=True)
        self.seen = self.participant(self.comp, 1)["updated_at"]  # what the phone shows

    def url(self, comp=None, adherent=1):
        return f"/api/competitions/{comp or self.comp}/participants/{adherent}"

    def queued(self, comp=None, adherent=1, seen=None, **flag):
        """PATCH as the phone's queue sends it: one flag and the `updated_at` it saw."""
        return self.client.patch(self.url(comp, adherent), json={**flag, "unchanged_since": seen or self.seen})

    def other_device_changes(self, **fields):
        """A write elsewhere (other coach, bureau page, desktop app, webhook) after the phone
        read the participant: its `updated_at` moves on."""
        Repo._update_participant(self.comp, 1, lambda p: p.update(fields, updated_at="2099-01-01T00:00:00"))

    def test_k1_unchanged_participant_is_applied(self):
        r = self.queued(selectionne=False)
        self.assertEqual(r.status_code, 200, r.text)
        p = self.participant(self.comp, 1)
        self.assertEqual((p["selectionne"], p["statut_paiement"]), (False, "non_invite"))

    def test_k2_same_value_set_meanwhile_is_accepted_without_write(self):
        self.other_device_changes(selectionne=False)
        before = Repo.get_competition_doc(self.comp)["updated_at"]
        r = self.queued(selectionne=False)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(Repo.get_competition_doc(self.comp)["updated_at"], before)

    def test_k3_participant_changed_meanwhile_is_refused(self):
        """Coach B unselected then selected again: the value is back to what A saw, but A's
        older « unselect » must not overwrite B's newer decision."""
        self.other_device_changes(selectionne=True)
        r = self.queued(selectionne=False)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "changed"))
        self.assertTrue(self.participant(self.comp, 1)["selectionne"])

        self.other_device_changes(present=False)
        r = self.queued(present=True)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "changed"))
        self.assertFalse(self.participant(self.comp, 1)["present"])

    def test_k3_changed_within_the_same_second_is_refused(self):
        """The office unselects and selects again in the second the phone read the participant (stamps of real
        writes, no forced date): to the second, the row looked unchanged and the phone's older change won."""
        ticks = (datetime.datetime(2026, 10, 23, 9, 57, 42, n) for n in range(1, 1000))
        clock = SimpleNamespace(datetime=SimpleNamespace(now=lambda: next(ticks)))
        with patch("infrastructure.firestore.competitions.base.datetime", clock):
            Repo.set_selection(self.comp, 1, True)  # the row the phone shows
            seen = self.participant(self.comp, 1)["updated_at"]
            Repo.set_selection(self.comp, 1, False)
            Repo.set_selection(self.comp, 1, True)
            self.assertEqual(self.participant(self.comp, 1)["updated_at"][:19], seen[:19])  # same second
            r = self.queued(selectionne=False, seen=seen)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "changed"))
        self.assertTrue(self.participant(self.comp, 1)["selectionne"])

    def test_k4_paid_meanwhile_unselect_is_refused(self):
        Repo.set_payment_status(self.comp, 1, PAIEMENT_PAYE)  # webhook: also a change of the row
        r = self.queued(selectionne=False)
        self.assertEqual(r.status_code, 409)
        self.assertIn(r.json()["code"], ("changed", "already_paid"))
        self.assertTrue(self.participant(self.comp, 1)["selectionne"])
        # Even with a fresh `updated_at`, a paid participant goes through the cancel flow
        r = self.queued(selectionne=False, seen=self.participant(self.comp, 1)["updated_at"])
        self.assertEqual((r.status_code, r.json()["code"]), (409, "already_paid"))

    def test_k5_removed_participant_or_deleted_competition(self):
        Repo.remove_participant_doc(self.comp, 1)
        for flag in ({"selectionne": False}, {"selectionne": True}, {"present": True}):
            self.assertEqual(self.queued(**flag).status_code, 404, flag)
        self.assertEqual(Repo.get_competition_doc(self.comp)["participants"], [])  # never re-added
        self.assertEqual(self.queued(comp=999, selectionne=False).status_code, 404)

    def test_k6_archived_competition_is_refused(self):
        self.client.patch(f"/api/competitions/{self.comp}", json={"statut": "close"})
        r = self.queued(selectionne=False)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "competition_closed"))
        self.assertTrue(self.participant(self.comp, 1)["selectionne"])
        # Online changes (no `unchanged_since`) keep today's behaviour
        self.assertEqual(self.client.patch(self.url(), json={"selectionne": False}).status_code, 200)

    def test_k9_replayed_request_is_harmless(self):
        for _ in range(2):
            r = self.queued(selectionne=False)
            self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(self.participant(self.comp, 1)["selectionne"])

    def test_online_writes_are_unchanged(self):
        self.other_device_changes(selectionne=True)
        self.assertEqual(self.client.patch(self.url(), json={"selectionne": False}).status_code, 200)
        self.assertFalse(self.participant(self.comp, 1)["selectionne"])

    def test_one_flag_per_queued_request(self):
        for body in ({"unchanged_since": self.seen},
                     {"selectionne": False, "present": True, "unchanged_since": self.seen},
                     {"selectionne": False, "unchanged_since": "x" * 65}):
            self.assertEqual(self.client.patch(self.url(), json=body).status_code, 422, body)
