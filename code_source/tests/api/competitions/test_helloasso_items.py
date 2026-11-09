"""Routes of src/api/competitions/helloasso_items.py over the in-memory Firestore (auth off, local server)."""

from support.api_case import ApiTestCase

from api.competitions.schemas.views import HelloAssoItem
from infrastructure.firestore.competitions import competitions, helloasso_items, participants


class TestHelloAssoItems(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.seed_adherent(1)
        self.comp = self.create(prix=15)["id"]
        self.fake.upsert_document("helloasso_items", "55", {
            "id_item": 55, "order_id": 9001, "montant": 15.0, "etat": "Processed",
            "date_item": "2026-03-01", "competition_id": None, "adherent_id": None,
            "source": None, "commentaire": ""})

    def link(self, **body):
        return self.client.put("/api/helloasso/items/55/link", json=body)

    def test_list_items(self):
        items = self.client.get("/api/helloasso/items").json()
        self.assertEqual([i["id_item"] for i in items], [55])
        self.assertNotIn("_doc_id", items[0])
        # The body is built by hand (json_with_etag): what it holds matches the contract
        parsed = HelloAssoItem.model_validate(items[0]).model_dump()
        self.assertEqual({k: parsed[k] for k in items[0] if k in HelloAssoItem.model_fields}, {k: v for k, v in items[0].items() if k in HelloAssoItem.model_fields})

    def test_ignore_and_link_answers(self):
        r = self.client.put("/api/helloasso/items/55/ignore", json={"ignore": True, "motif": "test"})
        self.assertEqual((r.status_code, r.json()), (200, {"status": "success"}))
        self.assertEqual(self.link(competition_id=self.comp, adherent_id=1).json(), {"status": "success", "linked": True})

    def test_link_records_payment_once(self):
        r = self.link(competition_id=self.comp, adherent_id=1, commentaire="ok")
        self.assertEqual(r.status_code, 200, r.text)
        item = helloasso_items.get_item(55)
        self.assertEqual((item["source"], item["commentaire"]), ("manuel", "ok"))
        p = self.participant(self.comp, 1)
        self.assertEqual((p["selectionne"], p["statut_paiement"], p["montant_paye"], p["commande_helloasso"]),
                         (True, "paye", 15.0, "9001"))
        # Saving the same link again does not count the amount twice (plan A1)
        self.link(competition_id=self.comp, adherent_id=1)
        self.assertEqual(self.participant(self.comp, 1)["montant_paye"], 15.0)

    def payment(self, adherent_id):
        p = self.participant(self.comp, adherent_id)
        return (p["selectionne"], p["statut_paiement"], p["montant_paye"], p["commande_helloasso"])

    def add_item(self, id_item, order_id, montant, etat="Processed", **link):
        self.fake.upsert_document("helloasso_items", str(id_item), {
            "id_item": id_item, "order_id": order_id, "montant": montant, "etat": etat,
            "date_item": "2026-03-02", "competition_id": None, "adherent_id": None,
            "source": None, "commentaire": "", **link})

    def test_unpaid_item_adds_the_member_without_payment(self):
        """A refunded or pending item is not money received (same rule as the automatic link)."""
        for etat in ("Refunded", "Pending"):
            with self.subTest(etat=etat):
                self.fake.upsert_document("helloasso_items", "55", dict(helloasso_items.get_item(55), etat=etat))
                self.assertEqual(self.link(competition_id=self.comp, adherent_id=1).status_code, 200)
                self.assertEqual(self.payment(1), (True, "en_attente", 0.0, ""))

    def test_amounts_of_all_linked_items_add_up(self):
        self.add_item(56, 9002, 5.0, competition_id=self.comp, adherent_id=1, source="auto")
        self.add_item(57, 9003, 30.0, etat="Refunded", competition_id=self.comp, adherent_id=1, source="auto")
        helloasso_items.apply_links_to_participants()
        self.assertEqual(self.payment(1), (True, "paye", 5.0, "9002"))
        self.link(competition_id=self.comp, adherent_id=1)
        selectionne, statut, montant, orders = self.payment(1)
        self.assertEqual((selectionne, statut, montant), (True, "paye", 20.0))
        self.assertEqual(sorted(orders.split(", ")), ["9001", "9002"])

    def test_relinking_moves_the_payment(self):
        self.seed_adherent(2)
        self.link(competition_id=self.comp, adherent_id=1)
        self.assertEqual(self.link(competition_id=self.comp, adherent_id=2).status_code, 200)
        self.assertEqual(self.payment(2), (True, "paye", 15.0, "9001"))
        self.assertEqual(self.payment(1), (True, "en_attente", 0.0, ""))

    def test_relinking_keeps_the_other_items_of_the_previous_member(self):
        self.seed_adherent(2)
        self.add_item(56, 9002, 5.0, competition_id=self.comp, adherent_id=1, source="auto")
        self.link(competition_id=self.comp, adherent_id=1)
        self.link(competition_id=self.comp, adherent_id=2)
        self.assertEqual(self.payment(1), (True, "paye", 5.0, "9002"))

    def test_partial_relink_undoes_the_payment(self):
        self.link(competition_id=self.comp, adherent_id=1)
        self.link(competition_id=self.comp)
        self.assertEqual(self.payment(1), (True, "en_attente", 0.0, ""))

    def test_relinking_keeps_a_cancellation(self):
        self.seed_adherent(2)
        self.link(competition_id=self.comp, adherent_id=1)
        participants.mark_cancelled_doc(self.comp, 1, "annule_reporte")
        self.link(competition_id=self.comp, adherent_id=2)
        self.assertEqual(self.participant(self.comp, 1)["statut_paiement"], "annule_reporte")
        self.assertEqual(self.payment(2), (True, "paye", 15.0, "9001"))

    def test_relinking_keeps_a_manual_payment_recorded_since(self):
        self.seed_adherent(2)
        self.link(competition_id=self.comp, adherent_id=1)
        participants.record_manual_payment_doc(self.comp, 1, 12.0)  # the coach got a cheque instead
        self.link(competition_id=self.comp, adherent_id=2)
        self.assertEqual(self.payment(1), (True, "paye", 12.0, "Règlement manuel"))

    def test_partial_link_and_errors(self):
        self.assertEqual(self.link(competition_id=self.comp).status_code, 200)
        item = helloasso_items.get_item(55)
        self.assertEqual((item["competition_id"], item["adherent_id"], item["source"]), (self.comp, None, None))
        self.assertEqual(competitions.get_competition_doc(self.comp)["participants"], [])
        self.assertEqual(self.link(competition_id=999, adherent_id=1).status_code, 404)
        self.assertEqual(self.client.put("/api/helloasso/items/77/link", json={}).status_code, 404)

    def test_ignore_and_restore(self):
        url = "/api/helloasso/items/55/ignore"
        r = self.client.put(url, json={"ignore": True})
        self.assertEqual((r.status_code, r.json()["code"]), (400, "motif_required"))
        self.assertEqual(self.client.put(url, json={"ignore": True, "motif": "Test"}).status_code, 200)
        item = helloasso_items.get_item(55)
        self.assertEqual((item["ignore"], item["ignore_motif"], item["commentaire"]), (True, "Test", "Test"))
        self.assertEqual(self.client.put(url, json={"ignore": False, "commentaire": "Erreur"}).status_code, 200)
        item = helloasso_items.get_item(55)
        self.assertEqual((item["ignore"], item["ignore_motif"], item["commentaire"]), (False, "", "Erreur"))

    def test_linked_item_cannot_be_ignored(self):
        self.link(competition_id=self.comp, adherent_id=1)
        r = self.client.put("/api/helloasso/items/55/ignore", json={"ignore": True, "motif": "Test"})
        self.assertEqual((r.status_code, r.json()["code"]), (409, "already_linked"))

    def test_ignore_sees_link_made_meanwhile(self):
        """The webhook links the item between the read and the write: the retry sees it."""
        def webhook_links(collection, doc_id):
            self.fake.before_conditional_write = None
            helloasso_items.set_item_link(55, self.comp, 1, source="webhook")
        self.fake.before_conditional_write = webhook_links
        r = self.client.put("/api/helloasso/items/55/ignore", json={"ignore": True, "motif": "Test"})
        self.assertEqual(r.status_code, 409)
        self.assertNotEqual(helloasso_items.get_item(55).get("ignore"), True)
