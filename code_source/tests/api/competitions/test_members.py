"""Routes of src/api/competitions/members.py over the in-memory Firestore (auth off, local server)."""

from unittest.mock import patch

from support.api_case import ApiTestCase

from api.competitions.schemas.views import CompetitionMember
from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
from infrastructure.firestore.client import FirestoreClient, FirestoreError


class TestCompetitionMembers(ApiTestCase):

    def test_projection(self):
        self.seed_adherent(1)
        members = self.client.get("/api/competition-members").json()
        self.assertEqual([(m["id"], m["nom"], m["licence_ffme"]) for m in members], [(1, "MARTIN", "654321")])
        # The body is built by hand (json_with_etag): the fields the contract declares are there, as declared
        declared = CompetitionMember.model_fields
        for m in members:
            self.assertEqual({k: v for k, v in CompetitionMember.model_validate(m).model_dump().items() if k in declared},
                             {k: m[k] for k in declared})

    def test_contacts_fields(self):
        self.seed_adherent(
            10,
            nom="DUPONT",
            prenom="Jean",
            phone="0612345678",
            emergency1_name="Dupont Marie",
            emergency1_phone="0611223344",
            emergency2_name="Dupont Pierre",
            emergency2_phone="0655667788",
            payer_name="Dupont Marie",
            payer_email="marie@test.fr",
        )
        (m,) = [x for x in self.client.get("/api/competition-members").json() if x["id"] == 10]
        self.assertEqual(m["phone"], "0612345678")
        self.assertEqual(m["emergency1_name"], "Dupont Marie")
        self.assertEqual(m["emergency1_phone"], "0611223344")
        self.assertEqual(m["emergency2_name"], "Dupont Pierre")
        self.assertEqual(m["emergency2_phone"], "0655667788")
        self.assertEqual(m["payer_name"], "Dupont Marie")
        self.assertEqual(m["payer_email"], "marie@test.fr")

    def test_status_filter(self):
        self.seed_adherent(1)
        self.seed_adherent(2, nom="DURAND", statut="Validé")
        self.seed_adherent(3, nom="PETIT", statut="Annulé")
        ids = lambda params: [m["id"] for m in self.client.get("/api/competition-members", params=params).json()]  # noqa: E731
        self.assertEqual(sorted(ids({})), [1, 2, 3])
        self.assertEqual(ids({"status": "Terminé"}), [1])
        self.assertEqual(sorted(ids({"status": ["Terminé", "Validé"]})), [1, 2])
        self.assertEqual(self.client.get("/api/competition-members", params={"status": "Terminé"}).json()[0]["statut"], "Terminé")
        self.assertEqual(self.client.get("/api/competition-members", params={"status": "Fini"}).status_code, 422)

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
