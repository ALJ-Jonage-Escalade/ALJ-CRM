"""Coaches (`coaches` collection) on an in-memory Firestore."""

from domain.competitions.models import Competition
from infrastructure.firestore.competitions import competitions
from infrastructure.firestore.competitions import coaches
from support.fake_firestore import FirestoreRepoTestCase


class TestCoaches(FirestoreRepoTestCase):
    def test_crud_and_competition_propagation(self):
        cid = coaches.save_coach("Adrien BERGER")
        self.assertEqual(coaches.get_coach(cid)["nom"], "Adrien BERGER")
        self.assertEqual([c["nom"] for c in coaches.list_coaches()], ["Adrien BERGER"])

        comp_id = competitions.save_competition(Competition(nom="Épreuve", coach_ids=[cid]))
        self.assertEqual(competitions.get_competition(comp_id).coach_ids, [cid])

        coaches.save_coach("Adrien BERGERAT", coach_id=cid)
        self.assertEqual(competitions.get_competition_doc(comp_id)["coaches"], ["Adrien BERGERAT"])  # renamed, nothing copied

        self.assertTrue(coaches.delete_coach(cid))
        comp_doc = self.fake.store["competitions"][str(comp_id)]
        self.assertEqual(comp_doc["coach_ids"], [])
        self.assertEqual(competitions.get_competition(comp_id).coach_ids, [])

    def test_get_unknown_coach(self):
        self.assertIsNone(coaches.get_coach(4242))
        self.assertFalse(coaches.delete_coach(4242))
