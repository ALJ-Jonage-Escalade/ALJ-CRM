"""Routes of src/api/competition_members.py over the in-memory Firestore (auth off, local server)."""

from unittest.mock import patch

from support.api_case import ApiTestCase

from infrastructure.competition_firestore_repository import CompetitionFirestoreRepository as Repo
from infrastructure.firestore_client import FirestoreClient, FirestoreError


class TestCompetitionMembers(ApiTestCase):

    def test_projection(self):
        self.seed_adherent(1)
        members = self.client.get("/api/competition-members").json()
        self.assertEqual([(m["id"], m["nom"], m["licence_ffme"]) for m in members], [(1, "MARTIN", "654321")])

    def test_firestore_failure_is_an_error_not_an_empty_directory(self):
        self.seed_adherent(1)
        with patch.object(FirestoreClient, "list_documents", side_effect=FirestoreError("down")):
            r = self.client.get("/api/competition-members")
        self.assertEqual((r.status_code, r.json()["code"]), (503, "unavailable"))
        # Nothing cached: the next request reads Firestore again
        self.assertEqual([m["id"] for m in self.client.get("/api/competition-members").json()], [1])

    def test_failure_of_any_kind_is_reported_as_unavailable(self):
        with patch.object(FirestoreClient, "list_documents", side_effect=ValueError("Identifiants manquants")):
            r = self.client.get("/api/competition-members")
        self.assertEqual(r.status_code, 503)

    def test_failed_refresh_keeps_the_last_copy(self):
        self.seed_adherent(1)
        self.client.get("/api/competition-members")
        Repo._adherents_cache_at = 0.0  # copy expired
        with patch.object(FirestoreClient, "list_documents", side_effect=FirestoreError("down")):
            r = self.client.get("/api/competition-members")
        self.assertEqual((r.status_code, [m["id"] for m in r.json()]), (200, [1]))
