"""HelloAsso mirror (`helloasso_items` collection) on an in-memory Firestore: upsert, links, payments carried over."""

from unittest.mock import patch

from domain.competitions.models import Competition
from infrastructure.firestore.client import FirestoreClient
from infrastructure.firestore.competitions import competitions, helloasso_items, participants
from support.fake_firestore import FirestoreRepoTestCase


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
        helloasso_items.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")

    def test_mirror_upsert_preserves_comment_and_link(self):
        written = helloasso_items.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")
        self.assertEqual(written, 1)

        self.fake.update_fields("helloasso_items", "500", {"commentaire": "Régularisation"})  # entered in the app
        helloasso_items.set_item_link(500, self.comp_id, 101, source="manuel")

        # Re-synchronisation : le commentaire et le lien sont conservés
        helloasso_items.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")
        it = helloasso_items.get_item(500)
        self.assertEqual(it["commentaire"], "Régularisation")
        self.assertEqual(it["competition_id"], self.comp_id)
        self.assertEqual(it["adherent_id"], 101)
        self.assertEqual(it["source"], "manuel")
        self.assertEqual(it["montant"], 15.0)
        self.assertEqual(str(it["order_id"]), "8888")

    def test_links_listing_and_clear(self):
        links = helloasso_items.list_helloasso_links()
        self.assertEqual(links, {})
        helloasso_items.set_item_link(500, self.comp_id, 101, source="manuel")
        links = helloasso_items.list_helloasso_links()
        self.assertEqual(links[500]["source"], "manuel")

        helloasso_items.save_manual_link(500, None, None)  # the coach clears the link
        self.assertEqual(helloasso_items.list_helloasso_links(), {})
        it = helloasso_items.get_item(500)
        self.assertIsNone(it["competition_id"])

    def test_replace_auto_links_preserves_manual(self):
        other_id = competitions.save_competition(Competition(nom="Autre épreuve", id_ffme="9999"))
        item2 = [{"id_item": 501, "payeur": "Léa DUPONT", "montant": 10.0, "etat": "Validated",
                  "date_item": "2026-02-02", "licence": "111222", "competition": "",
                  "commande": "7777"}]
        helloasso_items.update_helloasso_mirror(item2, [{"id": 501}], "campagne-2026")

        helloasso_items.replace_auto_links({
            500: {"competition_id": self.comp_id, "adherent_id": 101, "source": "auto"},
            501: {"competition_id": other_id, "adherent_id": None, "source": "auto"},
        })
        # Lien manuel posé ensuite sur 501 : non écrasé lors de la resynchronisation
        helloasso_items.set_item_link(501, other_id, None, source="manuel")
        helloasso_items.replace_auto_links({
            500: {"competition_id": self.comp_id, "adherent_id": 101, "source": "auto"},
        })
        it500 = helloasso_items.get_item(500)
        self.assertEqual(it500["source"], "auto")
        self.assertEqual(it500["competition_id"], self.comp_id)
        it501 = helloasso_items.get_item(501)
        self.assertEqual(it501["source"], "manuel")

    def test_apply_links_to_participants_aggregates(self):
        item2 = [{"id_item": 501, "payeur": "Lucas MARTIN", "montant": 15.0,
                  "etat": "Validated", "date_item": "2026-02-02", "licence": "654321",
                  "competition": "Coupe Rhône", "commande": "9999"}]
        helloasso_items.update_helloasso_mirror(item2, [{"id": 501}], "campagne-2026")
        helloasso_items.set_item_link(500, self.comp_id, 101, source="auto")
        helloasso_items.set_item_link(501, self.comp_id, 101, source="auto")

        applied = helloasso_items.apply_links_to_participants()
        self.assertEqual(applied, 1)
        p = participants.list_participants(self.comp_id)[0]
        self.assertEqual(p.statut_paiement, "paye")
        self.assertEqual(p.montant_paye, 30.0)
        self.assertEqual(p.commande_helloasso, "8888, 9999")
        self.assertTrue(p.selectionne)

    def test_unlinked_items_listing(self):
        helloasso_items.set_item_link(500, self.comp_id, None, source="auto")
        unlinked = helloasso_items.list_unlinked_items()
        self.assertEqual(len(unlinked), 1)
        row = unlinked[0]
        self.assertEqual(row["id_item"], 500)
        self.assertEqual(row["adherent_id"], 101)  # pré-sélection par licence

        helloasso_items.set_item_link(500, self.comp_id, 101, source="auto")
        self.assertEqual(helloasso_items.list_unlinked_items(), [])


    def _ignore(self, iid, motif="paiement de test"):
        self.fake.update_fields("helloasso_items", str(iid),
                                {"ignore": True, "ignore_motif": motif, "commentaire": motif})

    def test_ignored_item_excluded_from_unlinked_and_auto_links(self):
        self._ignore(500)
        self.assertEqual(helloasso_items.list_unlinked_items(), [])
        self.assertEqual(helloasso_items.list_helloasso_links()[500]["source"], "ignore")

        # Le moteur automatique ne rattache jamais une ligne ignorée
        from domain.competitions.matching import auto_link_items
        links = auto_link_items(
            [{"id_item": 500, "etat": "Validated", "competition": "18846", "licence": "654321"}],
            [{"id": self.comp_id, "id_ffme": "18846", "nom": "Coupe Rhône"}],
            [{"id": 101, "num_licence": "654321", "nom": "MARTIN", "prenom": "Lucas"}],
            helloasso_items.list_helloasso_links())
        self.assertEqual(links, {})
        helloasso_items.replace_auto_links({500: {"competition_id": self.comp_id, "adherent_id": 101, "source": "auto"}})
        it = helloasso_items.get_item(500)
        self.assertIsNone(it["competition_id"])
        self.assertTrue(it["ignore"])

    def test_resync_preserves_ignore_flag(self):
        self._ignore(500, "achat boutique")
        helloasso_items.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")
        it = helloasso_items.get_item(500)
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
            helloasso_items.update_helloasso_mirror(self.summary, self.raw, "campagne-2026")
        self.assertEqual(len(captured), 1)
        mask = captured[0]["update_fields"]
        for f in ("ignore", "commentaire", "competition_id", "adherent_id", "source"):
            self.assertNotIn(f, mask)
            self.assertNotIn(f, captured[0]["data"])

