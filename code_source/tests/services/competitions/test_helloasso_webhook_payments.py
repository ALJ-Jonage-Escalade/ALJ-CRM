"""HelloAsso webhook over the in-memory Firestore: the payments it records on participants."""

from unittest.mock import patch

from support.api_case import ApiTestCase

from infrastructure.firestore.competition_repository import CompetitionRepository
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from services.competitions.helloasso_webhook import HelloAssoWebhookService

REPO = "infrastructure.firestore.competition_repository.CompetitionRepository"


def payment_item(id_item: int, order_id: int, cents: int, state: str = "Processed") -> dict:
    return {
        "id": id_item, "amount": cents, "state": state,
        "order": {"id": order_id, "formSlug": "regularisation", "date": "2026-10-07T15:45:10+02:00"},
        "user": {"firstName": "Lucas", "lastName": "MARTIN"},
        "customFields": [
            {"name": "Numéro de licence FFME", "answer": "654321"},
            {"name": "Numéro de la compétition", "answer": "18846"},
        ],
    }


class TestWebhookPayments(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.seed_adherent(101)
        self.comp = self.create(id_ffme="18846", prix=15)["id"]
        for target, kwargs in (("infrastructure.firestore.app_settings.AppSettingsRepository.get", {"return_value": ""}),
                               ("services.competitions.helloasso_webhook.check_and_notify_all_paid",
                                {"return_value": False})):
            p = patch(target, **kwargs)
            p.start()
            self.addCleanup(p.stop)

    def receive(self, *items: dict) -> dict:
        report = HelloAssoWebhookService.reconcile_payment_items({"eventType": "Payment"}, items=list(items))
        self.assertEqual(report["matched_count"], len(items), report)
        return report

    def payment(self):
        p = self.participant(self.comp, 101)
        return p["selectionne"], p["statut_paiement"], p["montant_paye"], sorted(p["commande_helloasso"].split(", "))

    def test_first_payment_adds_the_participant(self):
        self.receive(payment_item(7777, 9999, 1500))
        self.assertEqual(self.payment(), (True, "paye", 15.0, ["9999"]))

    def test_second_payment_adds_up(self):
        self.receive(payment_item(7777, 9999, 1500))
        self.receive(payment_item(7778, 10000, 500))
        self.assertEqual(self.payment(), (True, "paye", 20.0, ["10000", "9999"]))
        self.receive(payment_item(7778, 10000, 500))  # HelloAsso delivers the notification again
        self.assertEqual(self.payment(), (True, "paye", 20.0, ["10000", "9999"]))

    def test_cancellation_reactivated_as_before(self):
        """Unchanged rule: a new HelloAsso payment for a cancelled participant reactivates them."""
        self.receive(payment_item(7777, 9999, 1500))
        CompetitionRepository.mark_cancelled(self.comp, 101, "annule_reporte")
        self.receive(payment_item(7778, 10000, 500))
        self.assertEqual(self.payment(), (True, "paye", 20.0, ["10000", "9999"]))

    def test_redelivered_payment_keeps_the_cancellation(self):
        """HelloAsso redelivers a notification already received: the coach's later cancellation is kept."""
        self.receive(payment_item(7777, 9999, 1500))
        CompetitionRepository.mark_cancelled(self.comp, 101, "annule_reporte")
        before = self.payment()
        self.receive(payment_item(7777, 9999, 1500))
        self.assertEqual(self.payment(), before)
        self.assertEqual(before[:2], (False, "annule_reporte"))

    def test_redelivered_payment_lists_a_member_removed_meanwhile(self):
        """A known item whose member is no longer listed: listed again, selected and paid (nothing to undo)."""
        self.receive(payment_item(7777, 9999, 1500))
        CompetitionRepository.remove_participant(self.comp, 101)
        self.receive(payment_item(7777, 9999, 1500))
        self.assertEqual(self.payment(), (True, "paye", 15.0, ["9999"]))

    def test_item_missing_from_the_mirror_records_its_own_amount(self):
        """Mirror write failed: the item cannot be added up with the others, its amount is kept."""
        with patch(f"{REPO}.update_helloasso_mirror", side_effect=RuntimeError("Firestore indisponible")):
            self.receive(payment_item(7777, 9999, 1500))
        self.assertEqual(self.payment(), (True, "paye", 15.0, ["9999"]))

    def test_member_list_unreadable_answers_an_error(self):
        """Without the member list the payment cannot be matched: the webhook answers an error
        status (not 200), so the failure shows on HelloAsso's side, and records nothing."""
        real = FirestoreClient.list_documents

        def adherents_down(collection, *args, **kwargs):
            if collection == CompetitionRepository.COLLECTION_ADHERENTS:
                raise FirestoreError("down")
            return real(collection, *args, **kwargs)
        CompetitionRepository._invalidate_adherents_cache()  # no copy of the list yet (the competition read in setUp keeps one)
        with patch.object(FirestoreClient, "list_documents", side_effect=adherents_down):
            r = self.client.post("/webhooks/helloasso", json={"eventType": "Payment", "data": payment_item(7777, 9999, 1500)})
        self.assertEqual(r.status_code, 503, r.text)
        self.assertEqual(r.json()["status"], "error")
        self.assertEqual(self.fake.list_documents("helloasso_items"), [])
        self.assertEqual(CompetitionRepository.get_competition_doc(self.comp)["participants"], [])
