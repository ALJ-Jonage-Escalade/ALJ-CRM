"""Payment status after a participant is checked or unchecked (payment_status_after_toggle)."""

import unittest
from domain.competitions.models import (
    payment_status_after_toggle,
    PAIEMENT_NON_INVITE,
    PAIEMENT_EN_ATTENTE,
    PAIEMENT_PAYE,
    PAIEMENT_ANNULE_PERDU,
    PAIEMENT_ANNULE_REPORTE,
)


class TestBasculeParticipePaiement(unittest.TestCase):
    """Règle de liaison « Participe » ↔ statut de paiement (hors décisions coach)."""

    def test_checking(self):
        self.assertEqual(payment_status_after_toggle(PAIEMENT_NON_INVITE, True), PAIEMENT_EN_ATTENTE)
        self.assertIsNone(payment_status_after_toggle(PAIEMENT_EN_ATTENTE, True))
        self.assertIsNone(payment_status_after_toggle(PAIEMENT_PAYE, True))
        # Réactivation d'un annulé : retour « payé » (l'argent est déjà là)
        self.assertEqual(payment_status_after_toggle(PAIEMENT_ANNULE_REPORTE, True), PAIEMENT_PAYE)
        self.assertEqual(payment_status_after_toggle(PAIEMENT_ANNULE_PERDU, True), PAIEMENT_PAYE)
        # Statut inconnu/vide traité comme « non invité » -> « en attente »
        self.assertEqual(payment_status_after_toggle(None, True), PAIEMENT_EN_ATTENTE)

    def test_unchecking(self):
        self.assertEqual(payment_status_after_toggle(PAIEMENT_EN_ATTENTE, False), PAIEMENT_NON_INVITE)
        self.assertIsNone(payment_status_after_toggle(PAIEMENT_NON_INVITE, False))
        # « payé » décoché = décision coach (dialog reporter/encaisser), pas de statut auto
        self.assertIsNone(payment_status_after_toggle(PAIEMENT_PAYE, False))
        self.assertIsNone(payment_status_after_toggle(PAIEMENT_ANNULE_REPORTE, False))
