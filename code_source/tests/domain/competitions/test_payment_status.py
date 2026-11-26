"""Payment status after a participant is checked or unchecked (payment_status_after_toggle)."""

import unittest

from domain.competitions.models import Competition, CompetitionStatus, Participant, PaymentStatus, payment_status_after_toggle


class TestBasculeParticipePaiement(unittest.TestCase):
    """Règle de liaison « Participe » ↔ statut de paiement (hors décisions coach)."""

    def test_checking(self):
        self.assertEqual(payment_status_after_toggle(PaymentStatus.NON_INVITE, True), PaymentStatus.EN_ATTENTE)
        self.assertIsNone(payment_status_after_toggle(PaymentStatus.EN_ATTENTE, True))
        self.assertIsNone(payment_status_after_toggle(PaymentStatus.PAYE, True))
        # Réactivation d'un annulé : retour « payé » (l'argent est déjà là)
        self.assertEqual(payment_status_after_toggle(PaymentStatus.ANNULE_REPORTE, True), PaymentStatus.PAYE)
        self.assertEqual(payment_status_after_toggle(PaymentStatus.ANNULE_PERDU, True), PaymentStatus.PAYE)
        # Statut inconnu/vide traité comme « non invité » -> « en attente »
        self.assertEqual(payment_status_after_toggle(None, True), PaymentStatus.EN_ATTENTE)

    def test_unchecking(self):
        self.assertEqual(payment_status_after_toggle(PaymentStatus.EN_ATTENTE, False), PaymentStatus.NON_INVITE)
        self.assertIsNone(payment_status_after_toggle(PaymentStatus.NON_INVITE, False))
        # « payé » décoché = décision coach (dialog reporter/encaisser), pas de statut auto
        self.assertIsNone(payment_status_after_toggle(PaymentStatus.PAYE, False))
        self.assertIsNone(payment_status_after_toggle(PaymentStatus.ANNULE_REPORTE, False))


class TestStoredStatus(unittest.TestCase):
    """Statuses read from a stored document become enum members; blank or unknown text gives the default."""

    def test_known_values_become_enum_members(self):
        self.assertIs(Competition.from_row({"statut": "close"}).statut, CompetitionStatus.CLOSE)
        self.assertIs(Participant.from_row({"statut_paiement": "annule_reporte"}).statut_paiement, PaymentStatus.ANNULE_REPORTE)

    def test_blank_or_unknown_values_give_the_default(self):
        for stored in (None, "", "archivee"):
            with self.subTest(stored=stored):
                self.assertIs(Competition.from_row({"statut": stored}).statut, CompetitionStatus.EN_PREPARATION)
                self.assertIs(Participant.from_row({"statut_paiement": stored}).statut_paiement, PaymentStatus.NON_INVITE)
