"""HelloAsso webhook over the in-memory Firestore: the payments it records on participants."""

from unittest.mock import patch

from support.api_case import ApiTestCase

from infrastructure.competition_firestore_repository import CompetitionFirestoreRepository as Repo
from infrastructure.helloasso_webhook_service import HelloAssoWebhookService

REPO = "infrastructure.competition_firestore_repository.CompetitionFirestoreRepository"


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
        for target, kwargs in ((f"{REPO}.get_app_setting", {"return_value": ""}),
                               ("infrastructure.helloasso_webhook_service.HelloAssoWebhookService.check_and_notify_all_paid",
                                {"return_value": False})):
            p = patch(target, **kwargs)
            p.start()
            self.addCleanup(p.stop)

    def receive(self, *items: dict) -> dict:
        report = HelloAssoWebhookService.process_webhook({"eventType": "Payment"}, items=list(items))
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
        Repo.mark_cancelled(self.comp, 101, "annule_reporte")
        self.receive(payment_item(7778, 10000, 500))
        self.assertEqual(self.payment(), (True, "paye", 20.0, ["10000", "9999"]))

    def test_item_missing_from_the_mirror_records_its_own_amount(self):
        """Mirror write failed: the item cannot be added up with the others, its amount is kept."""
        with patch(f"{REPO}.sync_helloasso_mirror", side_effect=RuntimeError("Firestore indisponible")):
            self.receive(payment_item(7777, 9999, 1500))
        self.assertEqual(self.payment(), (True, "paye", 15.0, ["9999"]))
