"""Daily results batch end to end: fake Firestore, fake MyCompet / FFME archive pages, e-mail patched, no network."""

from __future__ import annotations

import datetime
import itertools
from unittest.mock import patch

from domain.errors import StorageUnavailable, UpstreamUnavailable

from infrastructure.firestore.client import FirestoreError
from infrastructure.firestore.competitions import competitions
from services.competitions.results_batch import (
    FIELD_NEEDS_URL_NOTIFIED,
    SETTING_BATCH_WINDOW_DAYS,
    CompetitionResultsBatchService as Batch,
)
from support.fake_firestore import FirestoreRepoTestCase
from support.mycompet.render import results_url
from support.mycompet.web_stub import use_mycompet_stub

TODAY = datetime.date(2026, 10, 20)
ADA = {"adherent_id": 1, "nom": "ZORBALT", "prenom": "Quessa", "num_licence": "9980001", "selectionne": True}
BOB = {"adherent_id": 2, "nom": "PRIMSKAR", "prenom": "Taurin", "num_licence": "9980002", "selectionne": True}
OTHER = {"adherent_id": 3, "nom": "FENWOLDE", "prenom": "Elstrid", "num_licence": "9980003", "selectionne": True}


def days_ago(days: int) -> datetime.date:
    return TODAY - datetime.timedelta(days=days)


class BatchTestCase(FirestoreRepoTestCase):

    def setUp(self):
        super().setUp()
        self.web = use_mycompet_stub(self)
        send = patch("services.competitions.results_batch.EmailSender.send_email", return_value=True)
        self.send_email = send.start()
        self.addCleanup(send.stop)

    def competition(self, comp_id: int, nom: str, ended_days_ago: int, participants=(ADA, BOB, OTHER),
                    doc_id: str = "", **fields) -> None:
        doc = {"id": comp_id, "nom": nom, "lieu": "Valbrume", "date_competition": days_ago(ended_days_ago).isoformat(),
               "participants": [dict(p) for p in participants], **fields}
        self.fake.upsert_document("competitions", doc_id or str(comp_id), doc)

    def published(self, number: int, nom: str, ended_days_ago: int, in_archive: bool = True) -> None:
        """Results page with ADA 2nd in U13 Femme and BOB 5th in U15 Femme (OTHER did not compete)."""
        self.web.add_competition(number, nom, "Valbrume", days_ago(ended_days_ago), [
            {"nom": ADA["nom"], "prenom": ADA["prenom"], "licence": ADA["num_licence"], "categorie": "U13 Femme",
             "classement": 2},
            {"nom": BOB["nom"], "prenom": BOB["prenom"], "licence": BOB["num_licence"], "categorie": "U15 Femme",
             "classement": 5},
        ], in_archive=in_archive)

    def stored(self, comp_id: int) -> dict:
        return self.fake.store["competitions"][str(comp_id)]

    def run_batch(self, **kwargs) -> dict:
        kwargs.setdefault("today", TODAY)
        return Batch.run_daily_batch(**kwargs)


class TestDailyBatch(BatchTestCase):

    def test_results_found_through_the_archive_are_written_and_mailed(self):
        self.competition(101, "Open de bloc de Valbrume", ended_days_ago=3)
        self.published(99101, "Open de bloc de Valbrume", ended_days_ago=3)

        report = self.run_batch()

        self.assertEqual((report["competitions_checked"], report["competitions_updated"], report["partial"]), (1, 1, False))
        [detail] = report["details"]
        self.assertEqual((detail["status"], detail["url"]), ("found", results_url(99101)))
        doc = self.stored(101)
        self.assertEqual(doc["url_resultats"], results_url(99101))
        self.assertTrue(doc["resultats_synced_at"])
        ada, bob, other = doc["participants"]
        self.assertEqual((ada["classement"], ada["total_categorie"], ada["resultat_ffme"], ada["categorie_ffme"]),
                         ("2", 8, "2 / 8", "U13Femme"))
        self.assertEqual(bob["classement"], "5")
        self.assertNotIn("classement", other)
        self.assertEqual({k: ada[k] for k in ADA}, ADA)  # the other fields are left alone
        self.assertTrue(Batch.has_results(doc))
        self.send_email.assert_called_once()
        body = self.send_email.call_args.kwargs["html_body"]
        self.assertIn("ZORBALT", body)
        self.assertIn("Open de bloc de Valbrume", self.send_email.call_args.kwargs["subject"])
        self.assertEqual(self.web.archive_requests(), 1)

        self.send_email.reset_mock()
        self.assertEqual(self.run_batch()["competitions_checked"], 0)  # has results now: not searched again
        self.send_email.assert_not_called()

    def test_window_limits_the_competitions_searched(self):
        self.competition(201, "Open de bloc de Valbrume", ended_days_ago=5)
        self.competition(202, "Coupe de difficulté Brumevent", ended_days_ago=35)
        self.competition(203, "Futur contest", ended_days_ago=-10)
        self.competition(204, "Coupe d'il y a deux saisons", ended_days_ago=400)

        def checked(**kwargs) -> list:
            return [c["id"] for c in Batch.list_pending_competitions(today=TODAY, **kwargs)]

        self.assertEqual(checked(window_days=30), [201])
        self.assertEqual(checked(window_days=60), [201, 202])  # most recent first
        self.assertEqual(checked(window_days=365), [201, 202])
        self.assertEqual(checked(window_days=1, force=True), [201, 202])  # forced: one year back, not 204
        self.assertEqual(checked(), [201])  # default: 30 days
        self.fake.upsert_document("app_settings", SETTING_BATCH_WINDOW_DAYS, {"key": SETTING_BATCH_WINDOW_DAYS, "value": "45"})
        self.assertEqual(checked(), [201, 202])
        for invalid in ("abc", "0", "-3"):
            self.fake.upsert_document("app_settings", SETTING_BATCH_WINDOW_DAYS, {"key": SETTING_BATCH_WINDOW_DAYS, "value": invalid})
            self.assertEqual(Batch.get_window_days(), 30, invalid)
        self.assertEqual(self.run_batch(window_days=30)["window_days"], 30)

    def test_page_of_another_date_is_not_trusted(self):
        """A line with the same name and venue but another date (earlier season): nothing written, URL asked once."""
        self.competition(301, "Open de bloc de Valbrume", ended_days_ago=3)
        self.published(99301, "Open de bloc de Valbrume", ended_days_ago=200)

        report = self.run_batch()

        self.assertEqual(report["details"][0]["status"], "needs_url")
        doc = self.stored(301)
        self.assertNotIn("url_resultats", doc)
        self.assertNotIn("classement", doc["participants"][0])
        self.assertTrue(doc[FIELD_NEEDS_URL_NOTIFIED])
        self.send_email.assert_called_once()
        self.assertIn("URL à saisir manuellement", self.send_email.call_args.kwargs["html_body"])
        self.assertFalse([url for url in self.web.requested if url.endswith("resultat_99301")])  # page never fetched

        self.send_email.reset_mock()
        self.assertEqual(self.run_batch()["details"][0]["status"], "needs_url")
        self.send_email.assert_not_called()  # asked once, not every morning

    def test_url_entered_by_hand_is_trusted_without_the_archive(self):
        self.competition(401, "Championnat du club", ended_days_ago=2, url_resultats=results_url(99401))
        self.published(99401, "Autre nom sur MyCompet", ended_days_ago=40, in_archive=False)

        report = self.run_batch()

        self.assertEqual(report["details"][0]["status"], "found")
        self.assertEqual(self.web.archive_requests(), 0)  # every competition has its URL

    def test_competition_not_published_yet_stays_pending(self):
        self.competition(501, "Open de bloc de Valbrume", ended_days_ago=1)
        report = self.run_batch()
        self.assertEqual(report["details"][0]["status"], "pending")
        self.send_email.assert_not_called()

    def test_edit_made_during_the_run_is_kept(self):
        """The competition is re-read just before the write (optimistic lock): a web edit made meanwhile survives."""
        self.competition(601, "Open de bloc de Valbrume", ended_days_ago=3)
        self.published(99601, "Open de bloc de Valbrume", ended_days_ago=3)
        edits = iter([True])

        def coach_edits(collection, doc_id):
            if next(edits, False):
                doc = self.fake.store[collection][doc_id]
                doc["participants"][2]["selectionne"] = False
                doc["participants"].append({"adherent_id": 4, "nom": "NOUVEAU", "prenom": "Membre"})
                self.fake._touch(collection, doc_id)
        self.fake.before_conditional_write = coach_edits

        self.run_batch()

        parts = self.stored(601)["participants"]
        self.assertEqual(len(parts), 4)
        self.assertFalse(parts[2]["selectionne"])
        self.assertEqual(parts[0]["classement"], "2")

    def test_legacy_document_key_is_written_under_the_canonical_id(self):
        self.competition(701, "Open de bloc de Valbrume", ended_days_ago=3, doc_id="RandomLegacyKey")
        self.published(99701, "Open de bloc de Valbrume", ended_days_ago=3)

        self.run_batch()

        self.assertNotIn("RandomLegacyKey", self.fake.store["competitions"])
        self.assertEqual(self.stored(701)["participants"][0]["classement"], "2")

    def test_time_budget_stops_between_competitions(self):
        for comp_id, number in ((801, 99801), (802, 99802), (803, 99803)):
            self.competition(comp_id, f"Open de bloc numéro {comp_id}", ended_days_ago=comp_id - 800)
            self.published(number, f"Open de bloc numéro {comp_id}", ended_days_ago=comp_id - 800)
        clock = itertools.chain([0.0, 0.0], itertools.repeat(500.0))  # start, 1st competition, then past the budget

        report = self.run_batch(time_budget_s=150, clock=lambda: next(clock))

        self.assertEqual((report["competitions_checked"], report["competitions_remaining"], report["partial"]), (1, 2, True))
        self.assertEqual(report["details"][0]["id"], "801")  # most recent first
        self.assertEqual(self.run_batch()["competitions_checked"], 2)  # the next run goes on

    def test_one_failing_page_does_not_stop_the_others(self):
        self.competition(901, "Open de bloc de Valbrume", ended_days_ago=2)
        self.competition(902, "Coupe de difficulté Brumevent", ended_days_ago=4)
        self.published(99901, "Open de bloc de Valbrume", ended_days_ago=2)
        self.published(99902, "Coupe de difficulté Brumevent", ended_days_ago=4)
        self.web.failing[99901] = 500

        report = self.run_batch()

        self.assertEqual([d["status"] for d in report["details"]], ["error", "found"])
        self.assertNotIn("url_resultats", self.stored(901))

    def test_one_failing_save_does_not_stop_the_others(self):
        """Firestore refuses one competition's write: reported as an error, the others are still searched."""
        from unittest.mock import patch
        from infrastructure.firestore.client import FirestoreError
        from infrastructure.firestore.competitions import participants
        self.competition(911, "Open de bloc de Valbrume", ended_days_ago=2)
        self.competition(912, "Coupe de difficulté Brumevent", ended_days_ago=4)
        self.published(99911, "Open de bloc de Valbrume", ended_days_ago=2)
        self.published(99912, "Coupe de difficulté Brumevent", ended_days_ago=4)
        real = participants.record_results

        def record_results(competition_id, *args, **kwargs):
            if str(competition_id) == "911":
                raise FirestoreError("HTTP 500")
            return real(competition_id, *args, **kwargs)
        with patch.object(participants, "record_results", record_results):
            report = self.run_batch()

        self.assertEqual([d["status"] for d in report["details"]], ["error", "found"])
        self.assertEqual(report["competitions_updated"], 1)

    def test_archive_down_still_processes_hand_entered_urls(self):
        self.competition(1001, "Open de bloc de Valbrume", ended_days_ago=2)
        self.competition(1002, "Championnat du club", ended_days_ago=3, url_resultats=results_url(99902))
        self.published(99902, "Championnat du club", ended_days_ago=3, in_archive=False)
        with patch("services.competitions.results_batch.fetch_ffme_archive_entries", side_effect=UpstreamUnavailable("503")):
            report = self.run_batch()
        self.assertEqual([d["status"] for d in report["details"]], ["pending", "found"])

    def test_firestore_failure_is_raised_not_reported_as_success(self):
        with patch.object(competitions, "list_competition_docs", side_effect=FirestoreError("down")):
            with self.assertRaises(StorageUnavailable):
                self.run_batch()
        self.send_email.assert_not_called()
