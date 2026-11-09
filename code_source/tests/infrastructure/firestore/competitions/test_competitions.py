"""Competition documents on an in-memory Firestore: CRUD, coach ids, legacy documents normalized."""

from domain.competitions.models import Competition
from infrastructure.firestore.competitions import coaches, competitions
from support.fake_firestore import FirestoreRepoTestCase


class TestCompetitionsCrud(FirestoreRepoTestCase):
    def test_create_edit_list_delete(self):
        comp = Competition(nom="Coupe Rhône", id_ffme="18846", date_competition="2026-03-15",
                           prix=15.0, whatsapp_link="https://chat.whatsapp.com/testfirestore")
        comp_id = competitions.save_competition(comp)
        self.assertTrue(comp_id)
        self.assertIn(str(comp_id), self.fake.store["competitions"])

        got = competitions.get_competition(comp_id)
        self.assertEqual(got.nom, "Coupe Rhône")
        self.assertEqual(got.doc_id, str(comp_id))
        self.assertEqual(got.whatsapp_link, "https://chat.whatsapp.com/testfirestore")

        got.prix = 18.0
        got.whatsapp_link = "https://chat.whatsapp.com/updated"
        competitions.save_competition(got)
        saved = competitions.get_competition(comp_id)
        self.assertEqual(saved.prix, 18.0)
        self.assertEqual(saved.whatsapp_link, "https://chat.whatsapp.com/updated")
        # Une seule documentation de l'épreuve (pas de doublon)
        self.assertEqual(len(self.fake.store["competitions"]), 1)

        comps = competitions.list_competitions()
        self.assertEqual(len(comps), 1)
        self.assertTrue(competitions.delete_competition(comp_id))
        self.assertEqual(competitions.list_competitions(), [])
        self.assertFalse(competitions.delete_competition(comp_id))

    def test_coach_fields_roundtrip(self):
        ids = [1, 2, 3, 4]  # fixed ids: _new_id() repeats within a millisecond (A30)
        for cid, nom in zip(ids, "ABCD", strict=True):
            coaches.save_coach(nom, coach_id=cid)
        comp_id = competitions.save_competition(Competition(nom="Épreuve", coach_ids=ids[::-1]))
        self.assertEqual(competitions.get_competition(comp_id).coach_ids, ids[::-1])  # no limit, order kept
        doc = self.fake.store["competitions"][str(comp_id)]
        # Ids only (plan C2 step B): neither the legacy slots nor a copy of the names
        self.assertFalse({"coach1_id", "coach2_id", "coach3_id", "coaches"} & set(doc))
        self.assertEqual(competitions.get_competition_doc(comp_id)["coaches"], ["D", "C", "B", "A"])  # resolved when read

    def test_legacy_coach_slots_read(self):
        """A document from an older version, with only coach1_id..coach3_id."""
        a, b = coaches.save_coach("A", coach_id=1), coaches.save_coach("B", coach_id=2)
        self.fake.upsert_document("competitions", "5", {"id": 5, "nom": "Ancienne",
                                                        "coach1_id": b, "coach2_id": None, "coach3_id": a,
                                                        "coaches": ["nom périmé"]})
        self.assertEqual(competitions.get_competition(5).coach_ids, [b, a])
        doc = competitions.get_competition_doc(5)
        self.assertEqual((doc["coach_ids"], doc["coaches"]), ([b, a], ["B", "A"]))  # names resolved
        self.assertNotIn("coach1_id", doc)  # the API answer has coach_ids only

    def test_empty_coach_ids_ignore_stale_legacy_slots(self):
        """A document updated since plan C2 with every coach removed: its old slots must not bring them back."""
        a = coaches.save_coach("A", coach_id=1)
        self.fake.upsert_document("competitions", "6", {"id": 6, "nom": "Sans coach", "coach_ids": [], "coach1_id": a})
        self.assertEqual(competitions.get_competition(6).coach_ids, [])
        self.assertEqual(competitions.get_competition_doc(6)["coaches"], [])

    def test_legacy_doc_normalized_on_read(self):
        """Un document hérité (ID Firestore aléatoire) est recopié vers str(id)."""
        legacy_doc = {
            "id": 42, "nom": "Épreuve web", "prix": 10.0, "statut": "en_preparation",
            "participants": [], "coach_ids": [], "coaches": [],
            "updated_at": "2026-01-02T10:00:00", "created_at": "2026-01-02T10:00:00",
        }
        self.fake.store["competitions"] = {"randomLegacyId": dict(legacy_doc)}
        comp = competitions.get_competition(42)
        self.assertEqual(comp.nom, "Épreuve web")
        self.assertEqual(comp.doc_id, "42")
        self.assertNotIn("randomLegacyId", self.fake.store["competitions"])
        self.assertIn("42", self.fake.store["competitions"])

    def test_duplicate_docs_kept_newest(self):
        """Deux documents pour le même id : le plus récent gagne, l'autre est supprimé."""
        self.fake.store["competitions"] = {
            "7": {"id": 7, "nom": "Ancienne", "participants": [], "coach_ids": [],
                  "updated_at": "2026-01-01T00:00:00"},
            "legacy7": {"id": 7, "nom": "Récente", "participants": [], "coach_ids": [],
                        "updated_at": "2026-01-05T00:00:00"},
        }
        comps = competitions.list_competitions()
        self.assertEqual(len(comps), 1)
        self.assertEqual(comps[0].nom, "Récente")
        self.assertEqual(self.fake.store["competitions"]["7"]["nom"], "Récente")
        self.assertNotIn("legacy7", self.fake.store["competitions"])
