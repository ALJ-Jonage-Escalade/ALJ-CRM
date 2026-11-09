"""
Tests unitaires pour le référentiel des compétitions sur Firestore
(competition_firestore_repository.py), avec client Firestore simulé en mémoire.
"""

import os
import sys
from unittest.mock import patch

_tests_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src_dir = os.path.join(os.path.dirname(_tests_dir), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from infrastructure.firestore.client import FirestoreClient
from infrastructure.firestore.competition_repository import CompetitionRepository
from infrastructure.firestore.competitions import participants
from infrastructure.firestore.competitions import competitions
from support.fake_firestore import FirestoreRepoTestCase
from domain.competitions.models import (
    Competition,
)


class TestHelloAssoMirror(FirestoreRepoTestCase):
    def setUp(self):
        super().setUp()
        self.seed_adherent(101, licence="654321")
        self.comp_id = competitions.save_competition(
            Competition(nom="Coupe Rhône", id_ffme="18846", date_competition="2026-03-15"))
        self.summary = [{
            "id_item": 500, "payeur": "Lucas MARTIN", "montant": 15.0, "etat": "Validated",
            "date_item": "2026-02-01", "licence": "654321", "competition": "Coupe Rhône",
            "commande": "8888",
        }]
        self.raw = [{"id": 500, "amount": 1500}]
        CompetitionRepository.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")

    def test_mirror_upsert_preserves_comment_and_link(self):
        written = CompetitionRepository.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")
        self.assertEqual(written, 1)

        CompetitionRepository.save_item_comment(500, "Régularisation")
        CompetitionRepository.set_item_link(500, self.comp_id, 101, source="manuel")

        # Re-synchronisation : le commentaire et le lien sont conservés
        CompetitionRepository.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")
        it = CompetitionRepository.get_item(500)
        self.assertEqual(it["commentaire"], "Régularisation")
        self.assertEqual(it["competition_id"], self.comp_id)
        self.assertEqual(it["adherent_id"], 101)
        self.assertEqual(it["source"], "manuel")
        self.assertEqual(it["montant"], 15.0)
        self.assertEqual(str(it["order_id"]), "8888")

    def test_links_listing_and_clear(self):
        links = CompetitionRepository.list_helloasso_links()
        self.assertEqual(links, {})
        CompetitionRepository.set_item_link(500, self.comp_id, 101, source="manuel")
        links = CompetitionRepository.list_helloasso_links()
        self.assertEqual(links[500]["source"], "manuel")

        self.assertTrue(CompetitionRepository.clear_item_link(500))
        self.assertEqual(CompetitionRepository.list_helloasso_links(), {})
        it = CompetitionRepository.get_item(500)
        self.assertIsNone(it["competition_id"])

    def test_replace_auto_links_preserves_manual(self):
        other_id = competitions.save_competition(Competition(nom="Autre épreuve", id_ffme="9999"))
        item2 = [{"id_item": 501, "payeur": "Léa DUPONT", "montant": 10.0, "etat": "Validated",
                  "date_item": "2026-02-02", "licence": "111222", "competition": "",
                  "commande": "7777"}]
        CompetitionRepository.update_helloasso_mirror(item2, [{"id": 501}], "campagne-2026")

        CompetitionRepository.replace_auto_links({
            500: {"competition_id": self.comp_id, "adherent_id": 101, "source": "auto"},
            501: {"competition_id": other_id, "adherent_id": None, "source": "auto"},
        })
        # Lien manuel posé ensuite sur 501 : non écrasé lors de la resynchronisation
        CompetitionRepository.set_item_link(501, other_id, None, source="manuel")
        CompetitionRepository.replace_auto_links({
            500: {"competition_id": self.comp_id, "adherent_id": 101, "source": "auto"},
        })
        it500 = CompetitionRepository.get_item(500)
        self.assertEqual(it500["source"], "auto")
        self.assertEqual(it500["competition_id"], self.comp_id)
        it501 = CompetitionRepository.get_item(501)
        self.assertEqual(it501["source"], "manuel")

    def test_apply_links_to_participants_aggregates(self):
        item2 = [{"id_item": 501, "payeur": "Lucas MARTIN", "montant": 15.0,
                  "etat": "Validated", "date_item": "2026-02-02", "licence": "654321",
                  "competition": "Coupe Rhône", "commande": "9999"}]
        CompetitionRepository.update_helloasso_mirror(item2, [{"id": 501}], "campagne-2026")
        CompetitionRepository.set_item_link(500, self.comp_id, 101, source="auto")
        CompetitionRepository.set_item_link(501, self.comp_id, 101, source="auto")

        applied = CompetitionRepository.apply_links_to_participants()
        self.assertEqual(applied, 1)
        p = participants.list_participants(self.comp_id)[0]
        self.assertEqual(p.statut_paiement, "paye")
        self.assertEqual(p.montant_paye, 30.0)
        self.assertEqual(p.commande_helloasso, "8888, 9999")
        self.assertTrue(p.selectionne)

    def test_unlinked_items_listing(self):
        CompetitionRepository.set_item_link(500, self.comp_id, None, source="auto")
        unlinked = CompetitionRepository.list_unlinked_items()
        self.assertEqual(len(unlinked), 1)
        row = unlinked[0]
        self.assertEqual(row["id_item"], 500)
        self.assertEqual(row["adherent_id"], 101)  # pré-sélection par licence

        CompetitionRepository.set_item_link(500, self.comp_id, 101, source="auto")
        self.assertEqual(CompetitionRepository.list_unlinked_items(), [])


    def _ignore(self, iid, motif="paiement de test"):
        self.fake.update_fields("helloasso_items", str(iid),
                                {"ignore": True, "ignore_motif": motif, "commentaire": motif})

    def test_ignored_item_excluded_from_unlinked_and_auto_links(self):
        self._ignore(500)
        self.assertEqual(CompetitionRepository.list_unlinked_items(), [])
        self.assertEqual(CompetitionRepository.list_helloasso_links()[500]["source"], "ignore")

        # Le moteur automatique ne rattache jamais une ligne ignorée
        from domain.competitions.matching import auto_link_items
        links = auto_link_items(
            [{"id_item": 500, "etat": "Validated", "competition": "18846", "licence": "654321"}],
            [{"id": self.comp_id, "id_ffme": "18846", "nom": "Coupe Rhône"}],
            [{"id": 101, "num_licence": "654321", "nom": "MARTIN", "prenom": "Lucas"}],
            CompetitionRepository.list_helloasso_links())
        self.assertEqual(links, {})
        CompetitionRepository.replace_auto_links({500: {"competition_id": self.comp_id, "adherent_id": 101, "source": "auto"}})
        it = CompetitionRepository.get_item(500)
        self.assertIsNone(it["competition_id"])
        self.assertTrue(it["ignore"])

    def test_resync_preserves_ignore_flag(self):
        self._ignore(500, "achat boutique")
        CompetitionRepository.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")
        it = CompetitionRepository.get_item(500)
        self.assertTrue(it["ignore"])
        self.assertEqual(it["ignore_motif"], "achat boutique")
        self.assertEqual(it["commentaire"], "achat boutique")

    def test_resync_writes_only_helloasso_fields(self):
        captured = []
        real = self.fake.batch_upsert
        def spy(writes, **kw):
            captured.extend(writes)
            return real(writes, **kw)
        with patch.object(FirestoreClient, "batch_upsert", spy):
            CompetitionRepository.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")
        self.assertEqual(len(captured), 1)
        mask = captured[0]["update_fields"]
        for f in ("ignore", "commentaire", "competition_id", "adherent_id", "source"):
            self.assertNotIn(f, mask)
            self.assertNotIn(f, captured[0]["data"])

