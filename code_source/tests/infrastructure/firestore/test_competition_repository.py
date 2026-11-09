"""
Tests unitaires pour le référentiel des compétitions sur Firestore
(competition_firestore_repository.py), avec client Firestore simulé en mémoire.
"""

import os
import sys
import unittest
from unittest.mock import patch

_tests_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src_dir = os.path.join(os.path.dirname(_tests_dir), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from infrastructure.firestore.client import FirestoreClient
from infrastructure.firestore import client as fc
from infrastructure.firestore.competitions import documents
from infrastructure.firestore.competition_repository import CompetitionRepository
from infrastructure.firestore.competitions import competitions
from support.fake_firestore import FakeFirestore, FirestoreRepoTestCase  # noqa: F401
from domain.competitions.models import (
    Competition,
    payment_status_after_toggle,
    PAIEMENT_NON_INVITE,
    PAIEMENT_EN_ATTENTE,
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
        CompetitionRepository.add_participant(self.comp_id, 101)
        parts = CompetitionRepository.list_participants(self.comp_id)
        self.assertEqual(len(parts), 1)
        p = parts[0]
        self.assertEqual(p.adherent_id, 101)
        self.assertTrue(p.selectionne)
        self.assertEqual(p.statut_paiement, "en_attente")
        self.assertEqual(p.tarif, "Compétition U18")

        # Idempotent : pas de doublon
        CompetitionRepository.add_participant(self.comp_id, 101)
        self.assertEqual(len(CompetitionRepository.list_participants(self.comp_id)), 1)

        self.assertTrue(CompetitionRepository.set_selection(self.comp_id, 101, False))
        self.assertFalse(CompetitionRepository.list_participants(self.comp_id)[0].selectionne)

        self.assertTrue(CompetitionRepository.set_payment_status(self.comp_id, 101, "paye"))
        p = CompetitionRepository.list_participants(self.comp_id)[0]
        self.assertEqual(p.statut_paiement, "paye")

        self.assertTrue(CompetitionRepository.apply_helloasso_payment(self.comp_id, 101, 15.0,
                                                     order_ref="CMD-1"))
        p = CompetitionRepository.list_participants(self.comp_id)[0]
        self.assertEqual(p.montant_paye, 15.0)
        self.assertEqual(p.commande_helloasso, "CMD-1")
        self.assertTrue(p.date_synchro_helloasso)

        self.assertTrue(CompetitionRepository.remove_participant(self.comp_id, 101))
        self.assertFalse(CompetitionRepository.remove_participant(self.comp_id, 101))
        self.assertEqual(CompetitionRepository.list_participants(self.comp_id), [])

    def test_set_selection_creates_missing_participant(self):
        self.assertTrue(CompetitionRepository.set_selection(self.comp_id, 102, True))
        parts = CompetitionRepository.list_participants(self.comp_id)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].adherent_id, 102)

    def test_load_competition_group_only_competition_tarifs(self):
        n = CompetitionRepository.load_competition_group_into(self.comp_id)
        self.assertEqual(n, 1)  # seul MARTIN a un tarif « Compétition »
        parts = CompetitionRepository.list_participants(self.comp_id)
        self.assertEqual(len(parts), 1)
        p = parts[0]
        self.assertEqual(p.adherent_id, 101)
        self.assertFalse(p.selectionne)
        self.assertEqual(p.statut_paiement, PAIEMENT_NON_INVITE)

    def test_load_competition_group_with_statuses(self):
        self.seed_adherent(103, nom="PETIT", tarif="Compétition U15", statut="En cours")
        self.assertEqual(CompetitionRepository.load_competition_group_into(self.comp_id, ["Terminé"]), 1)
        self.assertEqual([p.adherent_id for p in CompetitionRepository.list_participants(self.comp_id)], [101])

    def test_list_participants_selected_only(self):
        CompetitionRepository.add_participant(self.comp_id, 101, selectionne=True)
        CompetitionRepository.add_participant(self.comp_id, 102, selectionne=False)
        self.assertEqual(len(CompetitionRepository.list_participants(self.comp_id, selected_only=True)), 1)
        self.assertEqual(len(CompetitionRepository.list_participants(self.comp_id)), 2)

    def test_unknown_competition(self):
        self.assertEqual(CompetitionRepository.list_participants(9999), [])
        self.assertFalse(CompetitionRepository.remove_participant(9999, 101))


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
        p = CompetitionRepository.list_participants(self.comp_id)[0]
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


class TestBatchUpsertCommitBody(unittest.TestCase):
    """Régression : :commit exige un nom de document RELATIF (projects/…/documents/…),
    pas une URL complète (HTTP 400 « lacks projects » vu en production)."""

    def test_commit_uses_relative_document_name(self):
        with patch.object(fc.requests, "post") as mock_post, \
             patch.object(FirestoreClient, "get_access_token", return_value="fake-token"):
            resp = mock_post.return_value
            resp.status_code = 200
            report = FirestoreClient.batch_upsert(
                [{"path": "adherents/131", "data": {"nom": "DUPONT"}}],
                project_id="smart-amplifier-510811-n6",
            )
        self.assertEqual(report["written"], 1)
        self.assertEqual(report["errors_count"], 0)
        body = mock_post.call_args.kwargs["json"]
        name = body["writes"][0]["update"]["name"]
        self.assertTrue(name.startswith("projects/"), name)
        self.assertEqual(
            name,
            "projects/smart-amplifier-510811-n6/databases/(default)/documents/adherents/131",
        )
        # Le :commit est bien appelé sur l'URL absolue du service
        self.assertIn("https://firestore.googleapis.com/v1/", mock_post.call_args.args[0])
        self.assertIn(":commit", mock_post.call_args.args[0])


class TestModificationsConcurrentes(FirestoreRepoTestCase):
    """Verrouillage optimiste des participants : une écriture concurrente
    (autre poste, page web, webhook HelloAsso) n'est jamais perdue."""

    def setUp(self):
        super().setUp()
        self.seed_adherent(101)
        self.seed_adherent(102, nom="DUPONT", prenom="Léa", licence="111222")
        self.comp_id = competitions.save_competition(Competition(nom="Épreuve C", prix=15.0))
        CompetitionRepository.add_participant(self.comp_id, 101)
        CompetitionRepository.add_participant(self.comp_id, 102)

    def _parts(self):
        return {p.adherent_id: p for p in CompetitionRepository.list_participants(self.comp_id)}

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
        CompetitionRepository.set_selection(self.comp_id, 102, False)
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
        state = self._concurrent_once(lambda: CompetitionRepository.add_participant(self.comp_id, 103))
        CompetitionRepository.apply_helloasso_payment(self.comp_id, 101, 15.0, order_ref="ORD-1")
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
                CompetitionRepository.set_payment_status(self.comp_id, 101, PAIEMENT_PAYE)

    def test_modification_epreuve_ne_reecrit_pas_les_participants(self):
        comp = competitions.get_competition(self.comp_id)          # lu avant le paiement
        CompetitionRepository.apply_helloasso_payment(self.comp_id, 101, 15.0)
        comp.prix = 20.0
        competitions.save_competition(comp)
        self.assertEqual(competitions.get_competition(self.comp_id).prix, 20.0)
        self.assertEqual(self._parts()[101].statut_paiement, PAIEMENT_PAYE)

    def test_add_participant_retourne_l_identifiant(self):
        self.seed_adherent(104, nom="PETIT", prenom="Zoé", licence="555666")
        self.assertEqual(CompetitionRepository.add_participant(self.comp_id, 104), 104)


class TestFirestoreClientPrecondition(unittest.TestCase):
    """Client REST : précondition `currentDocument.updateTime` et clés techniques."""

    def test_meta_keys_jamais_ecrites(self):
        fields = fc.dict_to_firestore_fields({"nom": "A", "_doc_id": "1", "_update_time": "t"})
        self.assertEqual(list(fields), ["nom"])

    def test_update_fields_envoie_la_precondition(self):
        """Precondition in the body of a :commit (the URL parameter is ignored by the emulator)."""
        with patch.object(fc.requests, "post") as mock_post, \
             patch.object(FirestoreClient, "get_access_token", return_value="tok"):
            mock_post.return_value.status_code = 200
            FirestoreClient.update_fields("competitions", "1", {"x": 1, "_update_time": "T"},
                                          project_id="p", expected_update_time="T0")
        self.assertTrue(mock_post.call_args.args[0].endswith("/projects/p/databases/(default)/documents:commit"))
        write = mock_post.call_args.kwargs["json"]["writes"][0]
        self.assertEqual(write["currentDocument"], {"updateTime": "T0"})
        self.assertEqual(write["updateMask"], {"fieldPaths": ["x"]})
        self.assertEqual(write["update"]["name"], "projects/p/databases/(default)/documents/competitions/1")
        self.assertEqual(list(write["update"]["fields"]), ["x"])

    def test_update_fields_without_precondition_uses_patch(self):
        with patch.object(fc.requests, "patch") as mock_patch, \
             patch.object(FirestoreClient, "get_access_token", return_value="tok"):
            mock_patch.return_value.status_code = 200
            FirestoreClient.update_fields("competitions", "1", {"x": 1}, project_id="p")
        params = mock_patch.call_args.kwargs["params"]
        self.assertEqual(params, [("updateMask.fieldPaths", "x")])

    def test_update_fields_conflit(self):
        with patch.object(fc.requests, "post") as mock_post, \
             patch.object(fc.requests, "patch") as mock_patch, \
             patch.object(FirestoreClient, "get_access_token", return_value="tok"):
            for mock in (mock_post, mock_patch):
                mock.return_value.status_code = 400
                mock.return_value.text = '{"error": {"status": "FAILED_PRECONDITION"}}'
            with self.assertRaises(fc.FirestoreConflictError):
                FirestoreClient.update_fields("competitions", "1", {"x": 1},
                                              project_id="p", expected_update_time="T0")
            # Sans précondition, une erreur 400 reste une erreur générique
            with self.assertRaises(fc.FirestoreError) as ctx:
                FirestoreClient.update_fields("competitions", "1", {"x": 1}, project_id="p")
            self.assertNotIsInstance(ctx.exception, fc.FirestoreConflictError)


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


class TestAnnulationParticipantPaye(FirestoreRepoTestCase):
    """Annulation d'un participant ayant payé : report = crédit, perdu = écarté."""

    def setUp(self):
        super().setUp()
        self.seed_adherent(101)
        self.comp_id = competitions.save_competition(
            Competition(nom="Épreuve", date_competition="2026-03-15", prix=15.0))
        CompetitionRepository.add_participant(self.comp_id, 101, selectionne=True)
        CompetitionRepository.apply_helloasso_payment(self.comp_id, 101, 15.0, order_ref="CMD-1")

    def test_annule_reporte_garde_le_montant(self):
        self.assertTrue(CompetitionRepository.mark_cancelled(self.comp_id, 101, PAIEMENT_ANNULE_REPORTE, "blessure"))
        p = CompetitionRepository.list_participants(self.comp_id)[0]
        self.assertFalse(p.selectionne)
        self.assertEqual(p.statut_paiement, PAIEMENT_ANNULE_REPORTE)
        self.assertEqual(p.montant_paye, 15.0)
        self.assertEqual(p.note_paiement, "blessure")


    def test_annule_perdu_garde_le_montant(self):
        self.assertTrue(CompetitionRepository.mark_cancelled(self.comp_id, 101, PAIEMENT_ANNULE_PERDU, "absence"))
        p = CompetitionRepository.list_participants(self.comp_id)[0]
        self.assertFalse(p.selectionne)
        self.assertEqual(p.statut_paiement, PAIEMENT_ANNULE_PERDU)
        self.assertEqual(p.montant_paye, 15.0)


    def test_resync_helloasso_ne_pas_repayer_un_annule(self):
        CompetitionRepository.mark_cancelled(self.comp_id, 101, PAIEMENT_ANNULE_REPORTE, "blessure")
        # Re-synchronisation HelloAsso (l'article payé est toujours validé) :
        # l'annulation explicite du coach ne doit pas être écrasée.
        self.assertFalse(CompetitionRepository.apply_helloasso_payment(self.comp_id, 101, 15.0, order_ref="CMD-1"))
        p = CompetitionRepository.list_participants(self.comp_id)[0]
        self.assertEqual(p.statut_paiement, PAIEMENT_ANNULE_REPORTE)
        self.assertFalse(p.selectionne)

    def test_reactivation_par_re_ajout(self):
        CompetitionRepository.mark_cancelled(self.comp_id, 101, PAIEMENT_ANNULE_REPORTE, "blessure")
        CompetitionRepository.add_participant(self.comp_id, 101, selectionne=True)
        p = CompetitionRepository.list_participants(self.comp_id)[0]
        self.assertTrue(p.selectionne)
        self.assertEqual(p.statut_paiement, PAIEMENT_PAYE)
        self.assertEqual(p.montant_paye, 15.0)
        self.assertEqual(p.note_paiement, "blessure")


if __name__ == "__main__":
    unittest.main()
