"""Tests du module de gestion des compétitions (rapprochement HelloAsso)."""
import unittest

from domain.helloasso_campaigns import parse_campaign_identifier
from domain.competitions.matching import (
    match_items_to_participants,
    extract_competition_number,
    extract_competition_name,
    competition_number_ok,
    summarize_items,
)


def _make_item(state="Validated", first="Jean", last="DUPONT", amount=1000, licence=None, order_id=1):
    item = {
        "state": state,
        "amount": amount,
        "user": {"firstName": first, "lastName": last},
        "order": {"id": order_id},
        "customFields": [],
    }
    if licence is not None:
        item["customFields"].append({"name": "Numéro de Licence FFME", "answer": licence})
    return item


class TestCampaignIdentifier(unittest.TestCase):
    def test_full_event_url(self):
        res = parse_campaign_identifier(
            "https://www.helloasso.com/associations/amicale-laique-de-jonage/evenements/competition-escalade-2026"
        )
        self.assertEqual(res["form_type"], "Event")
        self.assertEqual(res["slug"], "competition-escalade-2026")

    def test_full_form_url(self):
        res = parse_campaign_identifier(
            "https://www.helloasso.com/associations/amicale-laique-de-jonage/formulaires/Event/compete-u11"
        )
        self.assertEqual(res["form_type"], "Event")
        self.assertEqual(res["slug"], "compete-u11")

    def test_explicit_prefix(self):
        res = parse_campaign_identifier("Membership:ma-campagne")
        self.assertEqual(res["form_type"], "Membership")
        self.assertEqual(res["slug"], "ma-campagne")

    def test_bare_slug_defaults_to_event(self):
        res = parse_campaign_identifier(" competition-u13 ")
        self.assertEqual(res["form_type"], "Event")
        self.assertEqual(res["slug"], "competition-u13")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            parse_campaign_identifier("  ")


class TestMatching(unittest.TestCase):
    def setUp(self):
        self.participants = [
            {"adherent_id": 1, "nom": "DUPONT", "prenom": "Jean", "num_licence": "123456",
             "selectionne": 1, "statut_paiement": "en_attente", "montant_paye": 0.0},
            {"adherent_id": 2, "nom": "MARTIN", "prenom": "Léa", "num_licence": "789012",
             "selectionne": 1, "statut_paiement": "non_invite", "montant_paye": 0.0},
            {"adherent_id": 3, "nom": "BERTRAND", "prenom": "Anne-Sophie", "num_licence": "",
             "selectionne": 1, "statut_paiement": "en_attente", "montant_paye": 0.0},
        ]

    def test_match_by_licence(self):
        res = match_items_to_participants(
            [_make_item(licence="123456", order_id=101)], self.participants, prix_attendu=10.0
        )
        self.assertEqual(res["updates"], [(1, 10.0)])
        self.assertEqual(res["stats"]["nb_anomalies"], 0)

    def test_match_by_name_when_no_licence_field(self):
        # Anne-Sophie n'a pas de licence : le rapprochement par nom doit fonctionner
        res = match_items_to_participants(
            [_make_item(first="Anne-Sophie", last="BERTRAND", order_id=102)],
            self.participants, prix_attendu=10.0
        )
        self.assertEqual([(u[0]) for u in res["updates"]], [3])
        types = [a["type"] for a in res["anomalies"]]
        self.assertIn("paiement_sans_licence", types)

    def test_payment_with_unknown_licence(self):
        res = match_items_to_participants(
            [_make_item(licence="999999", first="X", last="Y", order_id=103)],
            self.participants, prix_attendu=10.0
        )
        self.assertEqual(res["updates"], [])
        self.assertIn("paiement_inconnu", [a["type"] for a in res["anomalies"]])

    def test_amount_mismatch(self):
        res = match_items_to_participants(
            [_make_item(licence="123456", amount=800, order_id=104)],
            self.participants, prix_attendu=10.0
        )
        self.assertEqual(res["updates"], [(1, 8.0)])
        self.assertIn("ecart_tarif", [a["type"] for a in res["anomalies"]])

    def test_duplicate_payments(self):
        res = match_items_to_participants(
            [_make_item(licence="123456", order_id=1), _make_item(licence="123456", order_id=2)],
            self.participants, prix_attendu=10.0
        )
        self.assertIn("doublon", [a["type"] for a in res["anomalies"]])

    def test_canceled_and_refunded_ignored(self):
        res = match_items_to_participants(
            [_make_item(state="Canceled", licence="123456", order_id=1),
             _make_item(state="Refunded", licence="789012", order_id=2)],
            self.participants, prix_attendu=10.0
        )
        self.assertEqual(res["updates"], [])
        self.assertIn("remboursement", [a["type"] for a in res["anomalies"]])

    def test_waiting_state_reported(self):
        res = match_items_to_participants(
            [_make_item(state="Waiting", licence="123456", order_id=1)],
            self.participants, prix_attendu=10.0
        )
        self.assertEqual(res["updates"], [])
        self.assertIn("paiement_non_finalise", [a["type"] for a in res["anomalies"]])


class TestCompetitionNumberCheck(unittest.TestCase):
    """Contrôle du champ « Compétition concernée » (n° d'épreuve) sur HelloAsso."""

    def setUp(self):
        self.participants = [
            {"adherent_id": 1, "nom": "DUPONT", "prenom": "Jean", "num_licence": "123456",
             "selectionne": 1, "statut_paiement": "en_attente", "montant_paye": 0.0},
        ]

    def test_extract_competition_number(self):
        item = {"customFields": [{"name": "Compétition concernée", "answer": " EVT-2026-001 "}]}
        self.assertEqual(extract_competition_number(item), "EVT-2026-001")
        item2 = {"customFields": [{"name": "Competition concernee", "value": "EVT-2026-002"}]}
        self.assertEqual(extract_competition_number(item2), "EVT-2026-002")
        # Test du nouveau champ d'identifiant précis ("Numéro de la compétition") (Nouveau !)
        item3 = {"customFields": [{"name": "Numéro de la compétition", "answer": "18866"}]}
        self.assertEqual(extract_competition_number(item3), "18866")
        # Champ absent ou autre champ : chaîne vide
        self.assertEqual(extract_competition_number({"customFields": []}), "")
        self.assertEqual(extract_competition_number({}), "")
        self.assertEqual(
            extract_competition_number({"customFields": [{"name": "Numéro de Licence FFME", "answer": "123"}]}),
            ""
        )
        # Mode strict (fallback=False) : uniquement le champ n°, pas de repli sur
        # « Compétition concernée » (affichage fidèle à HelloAsso)
        item_noseul = {"customFields": [{"name": "Compétition concernée", "answer": "Championnat départemental de Bloc à Jonage"}]}
        self.assertEqual(extract_competition_number(item_noseul), "Championnat départemental de Bloc à Jonage")
        self.assertEqual(extract_competition_number(item_noseul, fallback=False), "")

    def test_extract_competition_name(self):
        # Champ réel du formulaire HelloAsso (avec accents) : doit être trouvé
        item = {"customFields": [{"name": "Compétition concernée", "answer": "Coupe régionale de bloc Ambérieu"}]}
        self.assertEqual(extract_competition_name(item), "Coupe régionale de bloc Ambérieu")
        item2 = {"customFields": [{"name": "Competition concernee", "value": "Coupe du Rhône de bloc"}]}
        self.assertEqual(extract_competition_name(item2), "Coupe du Rhône de bloc")
        # Le champ « Numéro de la compétition » n'est PAS le nom de la compétition
        item3 = {"customFields": [{"name": "Numéro de la compétition", "answer": "18866"}]}
        self.assertEqual(extract_competition_name(item3), "")
        # Les deux champs ensemble : chacun son extracteur
        item4 = {"customFields": [
            {"name": "Compétition concernée", "answer": "Coupe régionale de bloc Ambérieu"},
            {"name": "Numéro de la compétition", "answer": "18866"},
        ]}
        self.assertEqual(extract_competition_name(item4), "Coupe régionale de bloc Ambérieu")
        self.assertEqual(extract_competition_number(item4), "18866")
        # Champ absent ou autre champ : chaîne vide
        self.assertEqual(extract_competition_name({"customFields": []}), "")
        self.assertEqual(extract_competition_name({}), "")
        self.assertEqual(
            extract_competition_name({"customFields": [{"name": "Numéro de Licence FFME", "answer": "123"}]}),
            ""
        )

    def test_competition_number_ok(self):
        self.assertTrue(competition_number_ok("EVT-2026-001", "EVT-2026-001"))
        self.assertTrue(competition_number_ok("Compétition n° EVT-2026-001", "EVT-2026-001"))
        self.assertTrue(competition_number_ok("", ""))          # contrôle désactivé
        self.assertFalse(competition_number_ok("", "EVT-2026-001"))   # champ vide
        self.assertFalse(competition_number_ok("EVT-2026-002", "EVT-2026-001"))

    def test_missing_number_goes_to_manual_review(self):
        res = match_items_to_participants(
            [_make_item(licence="123456", order_id=110)],
            self.participants, prix_attendu=10.0, no_competition="EVT-2026-001"
        )
        # PAS de mise à jour automatique : le paiement part en correction manuelle
        self.assertEqual(res["updates"], [])
        self.assertEqual(len(res["manual_review"]), 1)
        entry = res["manual_review"][0]
        self.assertEqual(entry["adherent_id"], 1)        # pré-sélectionné via la licence
        self.assertEqual(entry["montant"], 10.0)
        self.assertEqual(entry["valeur_champ"], "")
        self.assertIn("competition_manquante", [a["type"] for a in res["anomalies"]])
        self.assertEqual(res["stats"]["nb_manual_review"], 1)

    def test_wrong_number_goes_to_manual_review(self):
        item = _make_item(licence="123456", order_id=111)
        item["customFields"].append({"name": "Compétition concernée", "answer": "EVT-2026-002"})
        res = match_items_to_participants(
            [item], self.participants, prix_attendu=10.0, no_competition="EVT-2026-001"
        )
        self.assertEqual(res["updates"], [])
        self.assertEqual(res["manual_review"][0]["valeur_champ"], "EVT-2026-002")
        self.assertIn("competition_ecartee", [a["type"] for a in res["anomalies"]])

    def test_correct_number_applies_payment(self):
        item = _make_item(licence="123456", order_id=112)
        item["customFields"].append(
            {"name": "Compétition concernée", "value": "Compétition n° EVT-2026-001"}
        )
        res = match_items_to_participants(
            [item], self.participants, prix_attendu=10.0, no_competition="EVT-2026-001"
        )
        self.assertEqual(res["updates"], [(1, 10.0)])
        self.assertEqual(res["manual_review"], [])

    def test_check_skipped_without_expected_number(self):
        # id_ffme vide en base : le contrôle est désactivé (comportement historique)
        res = match_items_to_participants(
            [_make_item(licence="123456", order_id=113)],
            self.participants, prix_attendu=10.0, no_competition=""
        )
        self.assertEqual(res["updates"], [(1, 10.0)])
        self.assertEqual(res["manual_review"], [])


class TestSummarizeItems(unittest.TestCase):
    """Projection tabulaire des articles HelloAsso (valeurs à vide si absentes)."""

    def test_fields_left_blank_when_not_filled(self):
        item = {"id": 777, "state": "Validated", "amount": 1500, "date": "2026-09-16T10:00:00+02:00",
                "user": {"firstName": "Jean", "lastName": "DUPONT"},
                "order": {"id": 1912194742}, "customFields": []}
        rows = summarize_items([item])
        self.assertEqual(rows, [{
            "id_item": 777, "payeur": "DUPONT Jean", "montant": 15.0,
            "commande": "1912194742", "licence": "", "competition": "",
            "etat": "Validated", "date_item": "2026-09-16T10:00:00+02:00",
        }])

    def test_fields_extracted_when_present(self):
        item = {"id": 42, "state": "Processed", "amount": 1500,
                "user": {"firstName": "Léa", "lastName": "MARTIN"},
                "order": {"id": 42},
                "customFields": [
                    {"name": "Numéro de Licence FFME", "answer": "789012"},
                    {"name": "Compétition concernée", "answer": "EVT-2026-001"},
                ]}
        r = summarize_items([item])[0]
        self.assertEqual(r["licence"], "789012")
        self.assertEqual(r["competition"], "EVT-2026-001")

    def test_empty_input(self):
        self.assertEqual(summarize_items(None), [])
        self.assertEqual(summarize_items([]), [])


class TestAutoLinkItems(unittest.TestCase):
    """Liens automatiques article HelloAsso -> (compétition, adhérent)."""

    def setUp(self):
        self.c1, self.c2 = 1, 2
        self.comps = [{"id": 1, "id_ffme": "EVT-2026-001", "nom": "Coupe du Rhône"},
                      {"id": 2, "id_ffme": "EVT-2026-002", "nom": "Championnat"}]
        self.adherents = [{"id": 1, "nom": "DUPONT", "prenom": "Jean", "num_licence": "123456"},
                          {"id": 2, "nom": "MARTIN", "prenom": "Léa", "num_licence": "789012"}]

    @staticmethod
    def _item(id_item, etat="Validated", licence="", competition="", payeur="DUPONT Jean"):
        return {"id_item": id_item, "payeur": payeur, "montant": 15.0,
                "commande": str(1000 + id_item), "licence": licence,
                "competition": competition, "etat": etat, "date_item": "2026-09-16"}

    def test_auto_link_by_champ_then_licence(self):
        from domain.competitions.matching import auto_link_items
        items = [
            self._item(1, licence="123456", competition="EVT-2026-001"),
            self._item(2, licence="789012", competition="Championnat EVT-2026-002"),
        ]
        links = auto_link_items(items, self.comps, self.adherents)
        self.assertEqual(links[1], {"competition_id": self.c1, "adherent_id": 1, "source": "auto"})
        self.assertEqual(links[2], {"competition_id": self.c2, "adherent_id": 2, "source": "auto"})

    def test_auto_link_no_competition_skipped(self):
        from domain.competitions.matching import auto_link_items
        # champ vide ou inconnu : pas de lien automatique (rattachement manuel requis)
        items = [self._item(3, licence="123456", competition=""),
                 self._item(4, licence="123456", competition="Compétition inconnue")]
        links = auto_link_items(items, self.comps, self.adherents)
        self.assertEqual(links, {})

    def test_auto_link_preserves_manual_and_ignores_invalid_state(self):
        from domain.competitions.matching import auto_link_items
        items = [self._item(5, licence="123456", competition="EVT-2026-001"),
                 self._item(6, licence="789012", competition="EVT-2026-002"),
                 self._item(7, etat="Refunded", licence="789012", competition="EVT-2026-001")]
        links = auto_link_items(items, self.comps, self.adherents, {5: "manuel"})
        # 5 : manuel préservé ; 6 : auto ; 7 : état non payé ignoré
        self.assertEqual(list(links.keys()), [6])


class TestMatchAdherentByName(unittest.TestCase):
    """Pré-sélection du compétiteur par nom + prénom (ordre inversé accepté)."""

    ADHERENTS = [
        {"id": 1, "nom": "FANJAT", "prenom": "Gabin"},
        {"id": 2, "nom": "LOMBARD", "prenom": "Théo"},
        {"id": 3, "nom": "POLSNIELLI ROUSSET", "prenom": "Julie"},
    ]

    def test_exact_and_case_insensitive(self):
        from domain.competitions.matching import match_adherent_by_name
        self.assertEqual(match_adherent_by_name("FANJAT Gabin", self.ADHERENTS), 1)
        self.assertEqual(match_adherent_by_name("fanjat gabin", self.ADHERENTS), 1)

    def test_reversed_order(self):
        from domain.competitions.matching import match_adherent_by_name
        self.assertEqual(match_adherent_by_name("Gabin FANJAT", self.ADHERENTS), 1)

    def test_composed_names_and_no_match(self):
        from domain.competitions.matching import match_adherent_by_name
        self.assertEqual(match_adherent_by_name("POLSNIELLI ROUSSET Julie", self.ADHERENTS), 3)
        self.assertIsNone(match_adherent_by_name("Inconnu Total", self.ADHERENTS))
        self.assertIsNone(match_adherent_by_name("", self.ADHERENTS))
        self.assertIsNone(match_adherent_by_name("FANJAT Gabin", None))


class TestGroupForTarif(unittest.TestCase):
    """Rapprochement tarif -> groupe de créneau (regroupement de la liste Compétiteurs)."""

    PLANNING = [
        {"groupe": "Compétition - U11-U13", "helloasso_tarifs": ["Compétition U11-U13 - jeunes nés 2014-2016"]},
        {"groupe": "Compétition - U15-U17", "helloasso_tarifs": ["Compétition U15-U17"]},
        {"groupe": "Autonome - adultes", "helloasso_tarifs": ["Adultes autonomes"]},
    ]

    def test_group_found(self):
        from domain.activities.planning_groups import group_for_tarif
        self.assertEqual(group_for_tarif("Compétition U11-U13 - jeunes nés 2014-2016", self.PLANNING),
                         "Compétition - U11-U13")
        self.assertEqual(group_for_tarif("ADULTES AUTONOMES", self.PLANNING), "Autonome - adultes")

    def test_group_not_found_or_empty(self):
        from domain.activities.planning_groups import group_for_tarif
        self.assertEqual(group_for_tarif("Tarif inconnu", self.PLANNING), "")
        self.assertEqual(group_for_tarif("", self.PLANNING), "")
        self.assertEqual(group_for_tarif("Adultes autonomes", None), "")


if __name__ == "__main__":
    unittest.main()
