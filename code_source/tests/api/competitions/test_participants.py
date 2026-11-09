"""Routes of src/api/competitions/participants.py over the in-memory Firestore (auth off, local server)."""

from unittest.mock import patch

from support.api_case import ApiTestCase

from services.competitions import store as competition_store

from domain.competitions.models import PAIEMENT_PAYE
from infrastructure.firestore.competitions import participants
from infrastructure.firestore.competitions import competitions
from infrastructure.firestore.competitions import member_directory
from infrastructure.firestore.competitions import documents
from infrastructure.firestore.client import FirestoreClient


class TestParticipants(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.seed_adherent(1)
        self.seed_adherent(2, nom="DURAND", prenom="Léa", tarif="Loisir adulte")
        self.comp = self.create()["id"]

    def url(self, suffix=""):
        return f"/api/competitions/{self.comp}/participants{suffix}"

    def test_add_select_unselect(self):
        r = self.client.post(self.url(), json={"adherent_id": 1})
        self.assertEqual(r.status_code, 200, r.text)
        p = self.participant(self.comp, 1)
        self.assertTrue(p["selectionne"])
        self.assertEqual(p["statut_paiement"], "en_attente")
        self.assertEqual(r.json()["nb_selectionnes"], 1)

        r = self.client.patch(self.url("/1"), json={"selectionne": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.participant(self.comp, 1)["statut_paiement"], "non_invite")
        self.assertEqual(self.client.post("/api/competitions/999/participants",
                                          json={"adherent_id": 1}).status_code, 404)

    def listed_participant(self, adherent_id):
        comp = next(c for c in self.client.get("/api/competitions").json() if c["id"] == self.comp)
        return next(p for p in comp["participants"] if p["adherent_id"] == adherent_id)

    def test_sex_is_read_from_the_member(self):
        """The participant row holds no sex: the view reads the member's, so a correction shows at once."""
        self.seed_adherent(3, nom="WEASLEY", prenom="Ginny", sex="F")
        r = self.client.post(self.url(), json={"adherent_id": 3})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("sex", documents.load_comp_doc(self.comp)["participants"][0])  # not copied
        self.assertEqual(next(p for p in r.json()["participants"] if p["adherent_id"] == 3)["sex"], "F")
        self.assertEqual(self.listed_participant(3)["sex"], "F")

        self.seed_adherent(3, nom="WEASLEY", prenom="Ginny", sex=None)  # sex cleared on the member record
        competition_store.invalidate_cache()
        self.assertIsNone(self.listed_participant(3)["sex"])

    def test_sex_of_older_rows_and_directory(self):
        """Rows written before plans/sex-enum.md hold a copied `gender` (dropped); directory documents not
        rewritten since hold `gender` (read as a code)."""
        self.seed_adherent(3, gender="Femme")
        participants.add_participant(self.comp, 3)
        doc = documents.load_comp_doc(self.comp)
        doc["participants"][0]["gender"] = "Homme"
        self.fake.upsert_document("competitions", doc["_doc_id"], {k: v for k, v in doc.items() if k != "_doc_id"})
        competition_store.invalidate_cache()
        participant = self.listed_participant(3)
        self.assertEqual(participant["sex"], "F")
        self.assertNotIn("gender", participant)

    def reads_during(self, method, url, body=None):
        """(response, competition documents read, coaches collection reads) of one request."""
        member_directory.adherent_map()  # member directory already cached, as on a warm server
        with patch.object(FirestoreClient, "get_document", wraps=self.fake.get_document) as get, \
                patch.object(FirestoreClient, "list_documents", wraps=self.fake.list_documents) as lst:
            r = self.client.request(method, url, json=body)
        comp_reads = sum(1 for c in get.call_args_list if c.args[0] == "competitions")
        comp_reads += sum(1 for c in lst.call_args_list if c.args[0] == "competitions")
        coach_reads = sum(1 for c in lst.call_args_list if c.args[0] == "coaches")
        return r, comp_reads, coach_reads

    def test_each_write_reads_the_competition_once(self):
        """The answer is the document the write produced: no existence check before, no read after."""
        participants.add_participant(self.comp, 2)
        writes = [("POST", self.url(), {"adherent_id": 1}),
                  ("PATCH", self.url("/1"), {"selectionne": False}),
                  ("PATCH", self.url("/1"), {"present": True}),
                  ("POST", self.url("/1/manual-payment"), {"montant": 15}),
                  ("POST", self.url("/1/cancel"), {"mode": "reporte", "note": "blessure"}),
                  ("DELETE", self.url("/2"), None)]
        for method, url, body in writes:
            with self.subTest(method=method, url=url):
                r, comp_reads, coach_reads = self.reads_during(method, url, body)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual((comp_reads, coach_reads), (1, 1))
                stored = competitions.get_competition_doc(self.comp)
                for key in ("participants", "nb_participants", "nb_selectionnes", "nb_payes", "total_collecte", "updated_at"):
                    self.assertEqual(r.json()[key], stored[key], key)

    def test_write_without_change_answers_the_stored_competition(self):
        """Loading the group when everyone is listed writes nothing: the competition is read."""
        url = f"/api/competitions/{self.comp}/load-group"
        r, comp_reads, _ = self.reads_during("POST", url)
        self.assertEqual((r.status_code, r.json()["added"], comp_reads), (200, 1, 1))
        r, comp_reads, _ = self.reads_during("POST", url)
        self.assertEqual((r.status_code, r.json()["added"], comp_reads), (200, 0, 2))
        self.assertEqual([p["adherent_id"] for p in r.json()["competition"]["participants"]], [1])
        self.assertEqual(self.client.post("/api/competitions/999/load-group").status_code, 404)
        self.assertEqual(self.client.patch("/api/competitions/999/participants/1", json={"selectionne": False}).status_code, 404)
        r = self.client.patch("/api/competitions/999/participants/1", json={"present": True})
        self.assertEqual((r.status_code, r.json()["message"]), (404, "Compétition introuvable."))
        r = self.client.patch(self.url("/2"), json={"present": True})
        self.assertEqual((r.status_code, r.json()["message"]), (404, "Compétiteur absent de cette compétition."))

    def test_unselect_paid_participant_needs_cancellation(self):
        participants.add_participant(self.comp, 1)
        participants.update_participant(self.comp, 1, lambda row: row.update(statut_paiement=PAIEMENT_PAYE))
        r = self.client.patch(self.url("/1"), json={"selectionne": False})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "already_paid")
        self.assertTrue(self.participant(self.comp, 1)["selectionne"])

        r = self.client.post(self.url("/1/cancel"), json={"mode": "reporte", "note": "Blessure"})
        self.assertEqual(r.status_code, 200, r.text)
        p = self.participant(self.comp, 1)
        self.assertEqual((p["selectionne"], p["statut_paiement"], p["note_paiement"]),
                         (False, "annule_reporte", "Blessure"))

    def test_cancel_validation(self):
        participants.add_participant(self.comp, 1)
        self.assertEqual(self.client.post(self.url("/1/cancel"),
                                          json={"mode": "rembourse", "note": "x"}).status_code, 422)
        self.assertEqual(self.client.post(self.url("/1/cancel"),
                                          json={"mode": "perdu", "note": " "}).status_code, 422)
        self.assertEqual(self.client.post(self.url("/2/cancel"),
                                          json={"mode": "perdu", "note": "x"}).status_code, 404)

    def test_present_flag_and_remove(self):
        participants.add_participant(self.comp, 1)
        self.assertEqual(self.client.patch(self.url("/1"), json={"present": True}).status_code, 200)
        self.assertTrue(self.participant(self.comp, 1)["present"])
        self.assertEqual(self.client.patch(self.url("/2"), json={"present": True}).status_code, 404)

        self.assertEqual(self.client.delete(self.url("/1")).status_code, 200)
        self.assertEqual(competitions.get_competition_doc(self.comp)["participants"], [])
        self.assertEqual(self.client.delete(self.url("/1")).status_code, 404)

    def test_manual_payment_and_restore(self):
        participants.add_participant(self.comp, 1, selectionne=False)
        r = self.client.post(self.url("/1/manual-payment"), json={"montant": 12.5})
        self.assertEqual(r.status_code, 200, r.text)
        p = self.participant(self.comp, 1)
        self.assertEqual((p["selectionne"], p["statut_paiement"], p["montant_paye"], p["commande_helloasso"]),
                         (True, "paye", 12.5, "Règlement manuel"))
        self.assertEqual(r.json()["total_collecte"], 12.5)
        self.assertEqual(self.client.post(self.url("/2/manual-payment"), json={"montant": 10}).status_code, 404)
        self.assertEqual(self.client.post(self.url("/1/manual-payment"), json={"montant": 0}).status_code, 422)

        # Withdrawal, then restore: re-adding a cancelled participant makes them paid again
        self.client.post(self.url("/1/cancel"), json={"mode": "reporte", "note": "blessure"})
        self.assertEqual(self.participant(self.comp, 1)["statut_paiement"], "annule_reporte")
        self.client.post(self.url(), json={"adherent_id": 1, "selectionne": True})
        p = self.participant(self.comp, 1)
        self.assertEqual((p["selectionne"], p["statut_paiement"], p["montant_paye"]), (True, "paye", 12.5))

    def test_load_group(self):
        r = self.client.post(f"/api/competitions/{self.comp}/load-group")
        self.assertEqual(r.json()["added"], 1)  # only the « Compétition » tariff member
        self.assertEqual(self.participant(self.comp, 1)["statut_paiement"], "non_invite")
        self.assertEqual(self.client.post(f"/api/competitions/{self.comp}/load-group").json()["added"], 0)

    def test_load_group_with_status_filter(self):
        self.seed_adherent(3, nom="PETIT", prenom="Max", tarif="Compétition U15", statut="Validé")
        r = self.client.post(f"/api/competitions/{self.comp}/load-group", params={"status": ["Terminé"]})
        self.assertEqual((r.status_code, r.json()["added"]), (200, 1))
        self.assertEqual([p["adherent_id"] for p in r.json()["competition"]["participants"]], [1])
        r = self.client.post(f"/api/competitions/{self.comp}/load-group", params={"status": ["Terminé", "Validé"]})
        self.assertEqual(r.json()["added"], 1)  # PETIT
        r = self.client.post(f"/api/competitions/{self.comp}/load-group", params={"status": "Fini"})
        self.assertEqual(r.status_code, 422)
