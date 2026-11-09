"""Participant rows of a competition on an in-memory Firestore: writes, optimistic lock, cancellations."""

import unittest
from unittest.mock import patch
from infrastructure.firestore import client as fc
from infrastructure.firestore.competitions import competitions, documents, participants
from support.fake_firestore import FirestoreRepoTestCase
from domain.competitions.models import (
    Competition,
    PAIEMENT_NON_INVITE,
    PAIEMENT_PAYE,
    PAIEMENT_ANNULE_PERDU,
    PAIEMENT_ANNULE_REPORTE,
)


class TestParticipants(FirestoreRepoTestCase):
    def setUp(self):
        super().setUp()
        self.seed_adherent(101)
        self.seed_adherent(102, nom="DUPONT", prenom="Léa", licence="111222",
                           tarif="Loisir")
        self.comp_id = competitions.save_competition(Competition(nom="Épreuve A", prix=15.0))

    def test_add_selection_payment_remove(self):
        participants.add_participant(self.comp_id, 101)
        parts = participants.list_participants(self.comp_id)
        self.assertEqual(len(parts), 1)
        p = parts[0]
        self.assertEqual(p.adherent_id, 101)
        self.assertTrue(p.selectionne)
        self.assertEqual(p.statut_paiement, "en_attente")
        self.assertEqual(p.tarif, "Compétition U18")

        # Idempotent : pas de doublon
        participants.add_participant(self.comp_id, 101)
        self.assertEqual(len(participants.list_participants(self.comp_id)), 1)

        self.assertIsNotNone(participants.set_selection_doc(self.comp_id, 101, False))
        self.assertFalse(participants.list_participants(self.comp_id)[0].selectionne)

        self.assertIsNotNone(participants.update_participant(self.comp_id, 101, lambda row: row.update(statut_paiement="paye")))
        p = participants.list_participants(self.comp_id)[0]
        self.assertEqual(p.statut_paiement, "paye")

        self.assertTrue(participants.apply_helloasso_payment(self.comp_id, 101, 15.0,
                                                     order_ref="CMD-1"))
        p = participants.list_participants(self.comp_id)[0]
        self.assertEqual(p.montant_paye, 15.0)
        self.assertEqual(p.commande_helloasso, "CMD-1")
        self.assertTrue(p.date_synchro_helloasso)

        self.assertIsNotNone(participants.remove_participant_doc(self.comp_id, 101))
        self.assertIsNone(participants.remove_participant_doc(self.comp_id, 101))
        self.assertEqual(participants.list_participants(self.comp_id), [])

    def test_set_selection_creates_missing_participant(self):
        self.assertIsNotNone(participants.set_selection_doc(self.comp_id, 102, True))
        parts = participants.list_participants(self.comp_id)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].adherent_id, 102)

    def test_load_competition_group_only_competition_tarifs(self):
        n = participants.load_competition_group_doc(self.comp_id)[0]
        self.assertEqual(n, 1)  # seul MARTIN a un tarif « Compétition »
        parts = participants.list_participants(self.comp_id)
        self.assertEqual(len(parts), 1)
        p = parts[0]
        self.assertEqual(p.adherent_id, 101)
        self.assertFalse(p.selectionne)
        self.assertEqual(p.statut_paiement, PAIEMENT_NON_INVITE)

    def test_load_competition_group_with_statuses(self):
        self.seed_adherent(103, nom="PETIT", tarif="Compétition U15", statut="En cours")
        self.assertEqual(participants.load_competition_group_doc(self.comp_id, ["Terminé"])[0], 1)
        self.assertEqual([p.adherent_id for p in participants.list_participants(self.comp_id)], [101])

    def test_list_participants_selected_only(self):
        participants.add_participant(self.comp_id, 101, selectionne=True)
        participants.add_participant(self.comp_id, 102, selectionne=False)
        self.assertEqual(len(participants.list_participants(self.comp_id, selected_only=True)), 1)
        self.assertEqual(len(participants.list_participants(self.comp_id)), 2)

    def test_unknown_competition(self):
        self.assertEqual(participants.list_participants(9999), [])
        self.assertIsNone(participants.remove_participant_doc(9999, 101))


class TestModificationsConcurrentes(FirestoreRepoTestCase):
    """Verrouillage optimiste des participants : une écriture concurrente
    (autre poste, page web, webhook HelloAsso) n'est jamais perdue."""

    def setUp(self):
        super().setUp()
        self.seed_adherent(101)
        self.seed_adherent(102, nom="DUPONT", prenom="Léa", licence="111222")
        self.comp_id = competitions.save_competition(Competition(nom="Épreuve C", prix=15.0))
        participants.add_participant(self.comp_id, 101)
        participants.add_participant(self.comp_id, 102)

    def _parts(self):
        return {p.adherent_id: p for p in participants.list_participants(self.comp_id)}

    def _concurrent_once(self, action):
        """Exécute `action` (écriture directe) une seule fois, juste avant la
        prochaine écriture conditionnelle du référentiel."""
        state = {"done": False}

        def hook(collection_name, doc_id):
            if state["done"]:
                return
            state["done"] = True
            self.fake.before_conditional_write = None
            action()
        self.fake.before_conditional_write = hook
        return state

    def test_paiement_concurrent_preserve_par_la_selection(self):
        # Pendant que le bureau décoche 102, le webhook HelloAsso marque 101 payé.
        def webhook():
            doc = self.fake.store["competitions"][str(self.comp_id)]
            parts = [dict(p) for p in doc["participants"]]
            for p in parts:
                if p["adherent_id"] == 101:
                    p["statut_paiement"] = "paye"
                    p["montant_paye"] = 15.0
            self.fake.update_fields("competitions", str(self.comp_id), {"participants": parts})
        state = self._concurrent_once(webhook)
        participants.set_selection_doc(self.comp_id, 102, False)
        self.assertTrue(state["done"])
        parts = self._parts()
        self.assertEqual(parts[101].statut_paiement, PAIEMENT_PAYE)   # pas écrasé
        self.assertEqual(parts[101].montant_paye, 15.0)
        self.assertFalse(parts[102].selectionne)                       # modification rejouée
        doc = self.fake.store["competitions"][str(self.comp_id)]
        self.assertEqual(doc["nb_payes"], 1)
        self.assertEqual(doc["total_collecte"], 15.0)

    def test_ajout_concurrent_preserve(self):
        self.seed_adherent(103, nom="BERNARD", prenom="Tom", licence="333444")
        state = self._concurrent_once(lambda: participants.add_participant(self.comp_id, 103))
        participants.apply_helloasso_payment(self.comp_id, 101, 15.0, order_ref="ORD-1")
        self.assertTrue(state["done"])
        parts = self._parts()
        self.assertIn(103, parts)
        self.assertEqual(parts[101].statut_paiement, PAIEMENT_PAYE)

    def test_conflit_persistant_leve_une_erreur(self):
        def always(collection_name, doc_id):
            self.fake._touch(collection_name, doc_id)
        self.fake.before_conditional_write = always
        with patch.object(documents.time, "sleep"):
            with self.assertRaises(fc.FirestoreConflictError):
                participants.update_participant(self.comp_id, 101, lambda row: row.update(statut_paiement=PAIEMENT_PAYE))

    def test_modification_epreuve_ne_reecrit_pas_les_participants(self):
        comp = competitions.get_competition(self.comp_id)          # lu avant le paiement
        participants.apply_helloasso_payment(self.comp_id, 101, 15.0)
        comp.prix = 20.0
        competitions.save_competition(comp)
        self.assertEqual(competitions.get_competition(self.comp_id).prix, 20.0)
        self.assertEqual(self._parts()[101].statut_paiement, PAIEMENT_PAYE)

    def test_add_participant_retourne_l_identifiant(self):
        self.seed_adherent(104, nom="PETIT", prenom="Zoé", licence="555666")
        self.assertEqual(participants.add_participant(self.comp_id, 104), 104)


class TestAnnulationParticipantPaye(FirestoreRepoTestCase):
    """Annulation d'un participant ayant payé : report = crédit, perdu = écarté."""

    def setUp(self):
        super().setUp()
        self.seed_adherent(101)
        self.comp_id = competitions.save_competition(
            Competition(nom="Épreuve", date_competition="2026-03-15", prix=15.0))
        participants.add_participant(self.comp_id, 101, selectionne=True)
        participants.apply_helloasso_payment(self.comp_id, 101, 15.0, order_ref="CMD-1")

    def test_annule_reporte_garde_le_montant(self):
        self.assertIsNotNone(participants.mark_cancelled_doc(self.comp_id, 101, PAIEMENT_ANNULE_REPORTE, "blessure"))
        p = participants.list_participants(self.comp_id)[0]
        self.assertFalse(p.selectionne)
        self.assertEqual(p.statut_paiement, PAIEMENT_ANNULE_REPORTE)
        self.assertEqual(p.montant_paye, 15.0)
        self.assertEqual(p.note_paiement, "blessure")


    def test_annule_perdu_garde_le_montant(self):
        self.assertIsNotNone(participants.mark_cancelled_doc(self.comp_id, 101, PAIEMENT_ANNULE_PERDU, "absence"))
        p = participants.list_participants(self.comp_id)[0]
        self.assertFalse(p.selectionne)
        self.assertEqual(p.statut_paiement, PAIEMENT_ANNULE_PERDU)
        self.assertEqual(p.montant_paye, 15.0)


    def test_resync_helloasso_ne_pas_repayer_un_annule(self):
        participants.mark_cancelled_doc(self.comp_id, 101, PAIEMENT_ANNULE_REPORTE, "blessure")
        # Re-synchronisation HelloAsso (l'article payé est toujours validé) :
        # l'annulation explicite du coach ne doit pas être écrasée.
        self.assertFalse(participants.apply_helloasso_payment(self.comp_id, 101, 15.0, order_ref="CMD-1"))
        p = participants.list_participants(self.comp_id)[0]
        self.assertEqual(p.statut_paiement, PAIEMENT_ANNULE_REPORTE)
        self.assertFalse(p.selectionne)

    def test_reactivation_par_re_ajout(self):
        participants.mark_cancelled_doc(self.comp_id, 101, PAIEMENT_ANNULE_REPORTE, "blessure")
        participants.add_participant(self.comp_id, 101, selectionne=True)
        p = participants.list_participants(self.comp_id)[0]
        self.assertTrue(p.selectionne)
        self.assertEqual(p.statut_paiement, PAIEMENT_PAYE)
        self.assertEqual(p.montant_paye, 15.0)
        self.assertEqual(p.note_paiement, "blessure")


if __name__ == "__main__":
    unittest.main()
