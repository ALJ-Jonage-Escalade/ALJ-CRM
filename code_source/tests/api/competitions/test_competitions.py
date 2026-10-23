"""Routes of src/api/competitions/competitions.py over the in-memory Firestore (auth off, local server)."""

from unittest.mock import patch

from support.api_case import ApiTestCase

from api.competitions.schemas.views import Competition as CompetitionView, CompetitionParticipant
from domain.competitions.models import Competition
from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
from infrastructure.firestore.client import FirestoreError


class TestCompetitions(ApiTestCase):

    def test_create_list_and_etag(self):
        self.fake.upsert_document("coaches", "7", {"id": 7, "nom": "Alice"})
        doc = self.create(id_ffme="18846", date_competition="2026-03-15", prix=15,
                          coach_ids=[7], lieu="Lyon", type="Bloc")
        self.assertEqual((doc["coach_ids"], doc["coaches"]), ([7], ["Alice"]))
        self.assertEqual((doc["lieu"], doc["type"]), ("Lyon", "Bloc"))  # pass-through fields
        self.assertEqual(doc["participants"], [])
        self.assertNotIn("_update_time", doc)

        Repo.add_participant(doc["id"], 1)
        r = self.client.get("/api/competitions")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([c["id"] for c in r.json()], [doc["id"]])
        # The body is built by hand (json_with_etag): the fields the contract declares are all there, as declared
        listed = r.json()[0]
        parsed = CompetitionView.model_validate(listed).model_dump()
        for field in CompetitionView.model_fields:
            if field in ("lieu", "type"):  # pass-through fields, only when the office page sent them
                continue
            self.assertIn(field, listed)
            if field != "participants":
                self.assertEqual(parsed[field], listed[field], field)
        (part,) = listed["participants"]
        for field in CompetitionParticipant.model_fields:
            # Set by the results fetch, or by a check-in, only
            if field not in ("classement", "total_categorie", "categorie_ffme", "resultat_ffme", "present"):
                self.assertIn(field, part)
                self.assertEqual(parsed["participants"][0][field], part[field], field)
        again = self.client.get("/api/competitions", headers={"If-None-Match": r.headers["etag"]})
        self.assertEqual(again.status_code, 304)

    def test_any_number_of_coaches(self):
        """No 3-coach limit; duplicates dropped, order kept (plan cleanup C2)."""
        for i in range(1, 6):
            self.fake.upsert_document("coaches", str(i), {"id": i, "nom": f"Coach {i}"})
        doc = self.create(coach_ids=[5, 1, 4, 1, 2, 3])
        self.assertEqual(doc["coach_ids"], [5, 1, 4, 2, 3])
        self.assertEqual(doc["coaches"], ["Coach 5", "Coach 1", "Coach 4", "Coach 2", "Coach 3"])
        r = self.client.patch(f"/api/competitions/{doc['id']}", json={"coach_ids": [3]})
        self.assertEqual(r.json()["coach_ids"], [3])

    def test_create_validation(self):
        for body in ({"nom": "  "}, {"nom": "A", "coach_ids": ["x"]},
                     {"nom": "A", "statut": "inconnu"}, {"nom": "A", "date_competition": "15/03/2026"},
                     {"nom": "A", "prix": -1}, {"nom": "A", "champ_inconnu": 1}):
            self.assertEqual(self.client.post("/api/competitions", json=body).status_code, 422, body)

    def test_partial_update_keeps_other_fields(self):
        doc = self.create(id_ffme="18846", helloasso_ref="coupe-rhone", lieu="Lyon")
        r = self.client.patch(f"/api/competitions/{doc['id']}", json={"nom": "Coupe du Rhône"})
        self.assertEqual(r.status_code, 200, r.text)
        updated = r.json()
        self.assertEqual(updated["nom"], "Coupe du Rhône")
        self.assertEqual(updated["id_ffme"], "18846")
        self.assertEqual(updated["helloasso_ref"], "coupe-rhone")
        self.assertEqual(updated["lieu"], "Lyon")
        self.assertEqual(self.client.patch("/api/competitions/123", json={"nom": "X"}).status_code, 404)

    def test_results_url_kept_by_other_updates(self):
        doc = self.create(url_resultats="https://mycompet.ffme.fr/resultat/resultat_13660")
        self.assertEqual(doc["url_resultats"], "https://mycompet.ffme.fr/resultat/resultat_13660")
        r = self.client.patch(f"/api/competitions/{doc['id']}", json={"prix": 20})
        self.assertEqual(r.json()["url_resultats"], "https://mycompet.ffme.fr/resultat/resultat_13660")

    def test_update_keeps_a_field_written_meanwhile(self):
        """The results batch writes the results URL between the PATCH's read and its write: the
        write is refused on the stale version, the PATCH re-reads and keeps the URL."""
        doc = self.create(nom="Coupe", prix=15)

        def batch_writes_results(collection, doc_id):
            self.fake.before_conditional_write = None
            self.fake.update_fields("competitions", doc_id, {"url_resultats": "https://mycompet.ffme.fr/resultat/42",
                                                            "resultats_synced_at": "2026-10-18T07:00:00"})
        self.fake.before_conditional_write = batch_writes_results
        r = self.client.patch(f"/api/competitions/{doc['id']}", json={"nom": "Coupe du Rhône"})
        self.assertEqual(r.status_code, 200, r.text)
        stored = Repo.get_competition_doc(doc["id"])
        self.assertEqual((stored["nom"], stored["prix"], stored["url_resultats"], stored["resultats_synced_at"]),
                         ("Coupe du Rhône", 15.0, "https://mycompet.ffme.fr/resultat/42", "2026-10-18T07:00:00"))

    def test_update_keeps_participants_added_meanwhile(self):
        self.seed_adherent(1)
        doc = self.create()

        def coach_adds_participant(collection, doc_id):
            self.fake.before_conditional_write = None
            Repo.add_participant(doc["id"], 1)
        self.fake.before_conditional_write = coach_adds_participant
        self.assertEqual(self.client.patch(f"/api/competitions/{doc['id']}", json={"prix": 20}).status_code, 200)
        stored = Repo.get_competition_doc(doc["id"])
        self.assertEqual(([p["adherent_id"] for p in stored["participants"]], stored["nb_participants"], stored["prix"]),
                         ([1], 1, 20.0))

    def test_update_keeps_participants(self):
        self.seed_adherent(1)
        doc = self.create()
        Repo.add_participant(doc["id"], 1)
        r = self.client.patch(f"/api/competitions/{doc['id']}", json={"statut": "close"})
        self.assertEqual(r.json()["statut"], "close")
        self.assertEqual(len(r.json()["participants"]), 1)

    def test_delete(self):
        doc = self.create()
        self.assertEqual(self.client.delete(f"/api/competitions/{doc['id']}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/competitions/{doc['id']}").status_code, 404)
        self.assertEqual(self.client.get("/api/competitions").json(), [])

    def test_archive_past(self):
        # Explicit ids: new ids are millisecond timestamps, equal within one test
        past = Repo.save_competition(Competition(id=1, nom="Passée", date_competition="2020-01-10"))
        two_days = Repo.save_competition(Competition(id=2, nom="Longue", date_competition="2020-01-10",
                                                     date_fin="2999-01-11"))
        undated = Repo.save_competition(Competition(id=3, nom="Sans date"))
        r = self.client.post("/api/competitions/archive-past")
        self.assertEqual(r.json()["archived"], [past])
        self.assertEqual(Repo.get_competition(past).statut, "close")
        self.assertEqual(Repo.get_competition(two_days).statut, "en_preparation")
        self.assertEqual(Repo.get_competition(undated).statut, "en_preparation")

    def test_firestore_failure(self):
        with patch.object(Repo, "list_competition_docs", side_effect=FirestoreError("down")):
            r = self.client.get("/api/competitions")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["code"], "unavailable")
