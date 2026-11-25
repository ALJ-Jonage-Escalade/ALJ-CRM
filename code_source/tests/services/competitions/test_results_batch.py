"""
Tests unitaires pour CompetitionResultsBatchService.
Vérifie la détection des compétitions passées sans résultats, la configuration de l'e-mail,
le scraping mocké, la génération de l'e-mail HTML et l'envoi de notification.
"""

import datetime
import unittest
from unittest.mock import patch

from domain.club_emails import DEFAULT_RESULTS_NOTIFICATION_EMAIL
from domain.competitions.results import apply_rankings, has_results, is_competition_past
from domain.errors import InvalidRequest
from services.competitions.results_batch import CompetitionResultsBatchService
from services.competitions.results_email import results_email_html
from support.fake_firestore import use_fake_firestore


class TestCompetitionResultsBatchService(unittest.TestCase):

    def setUp(self):
        use_fake_firestore(self)  # notification e-mail setting

    def test_default_notification_email(self):
        """Sans réglage, l'adresse de notification est celle par défaut du club."""
        email = CompetitionResultsBatchService.get_notification_email()
        self.assertIn("@", email)
        self.assertEqual(email, DEFAULT_RESULTS_NOTIFICATION_EMAIL)

    def test_set_and_get_custom_notification_email(self):
        """L'adresse de notification peut être mise à jour et rechargée depuis les réglages."""
        custom_email = "notif.test@alj-jonage.fr"
        CompetitionResultsBatchService.update_settings(custom_email)
        self.assertEqual(CompetitionResultsBatchService.get_notification_email(), custom_email)

    def test_set_and_get_multiple_notification_emails(self):
        """Plusieurs adresses de notification peuvent être enregistrées et normalisées."""
        emails_input = "coach1@alj-jonage.fr, coach2@alj-jonage.fr; admin@alj-jonage.fr"
        CompetitionResultsBatchService.update_settings(emails_input)
        expected = "coach1@alj-jonage.fr, coach2@alj-jonage.fr, admin@alj-jonage.fr"
        self.assertEqual(CompetitionResultsBatchService.get_notification_email(), expected)

        parsed = CompetitionResultsBatchService.parse_notification_emails(emails_input)
        self.assertEqual(parsed, ["coach1@alj-jonage.fr", "coach2@alj-jonage.fr", "admin@alj-jonage.fr"])

    def test_set_invalid_email_raises_error(self):
        """Une adresse sans @ ou invalide est refusée (InvalidRequest), rien n'est enregistré."""
        with self.assertRaises(InvalidRequest):
            CompetitionResultsBatchService.update_settings("adresse_invalide")
        self.assertEqual(CompetitionResultsBatchService.get_notification_email(), DEFAULT_RESULTS_NOTIFICATION_EMAIL)

    def test_is_competition_past(self):
        """Vérifie le calcul de date pour déterminer si une épreuve est passée."""
        today = datetime.date(2026, 10, 14)

        # 1. Compétition hier -> passée
        comp_past = {"nom": "Open Passé", "date_competition": "2026-10-10"}
        self.assertTrue(is_competition_past(comp_past, today=today))

        # 2. Compétition aujourd'hui -> passée / en cours
        comp_today = {"nom": "Open Aujourd'hui", "date_competition": "2026-10-14"}
        self.assertTrue(is_competition_past(comp_today, today=today))

        # 3. Compétition future -> non passée
        comp_future = {"nom": "Open Futur", "date_competition": "2026-11-20"}
        self.assertFalse(is_competition_past(comp_future, today=today))

        # 4. Compétition multi-jours avec date_fin dans le futur -> non passée
        comp_multi = {"nom": "Championnat", "date_competition": "2026-10-10", "date_fin": "2026-10-18"}
        self.assertFalse(is_competition_past(comp_multi, today=today))

    def test_has_results(self):
        """Vérifie la détection de présence ou d'absence de résultats."""
        # 1. Aucun classement et pas de synchro -> pas de résultat
        comp_no_res = {
            "nom": "Open 1",
            "participants": [{"nom": "DUPONT", "prenom": "Jean", "classement": ""}],
            "resultats_synced_at": ""
        }
        self.assertFalse(has_results(comp_no_res))

        # 2. Classement et synchro présents -> a des résultats
        comp_with_res = {
            "nom": "Open 2",
            "participants": [{"nom": "DUPONT", "prenom": "Jean", "classement": "2"}],
            "resultats_synced_at": "2026-10-11T18:00:00"
        }
        self.assertTrue(has_results(comp_with_res))

    def test_build_results_email_html_structure(self):
        """Le générateur d'e-mail HTML produit un tableau structuré avec médailles et liens."""
        comp_data = [{
            "id": "comp_10",
            "nom": "Open Régional Bloc Jonage",
            "date": "2026-10-10",
            "lieu": "Jonage",
            "url": "https://mycompet.ffme.fr/resultat/resultat_13660",
            "athletes": [
                {
                    "nom": "BULAND",
                    "prenom": "Julia",
                    "num_licence": "930654",
                    "categorie": "U15 Femme",
                    "classement": "1",
                    "total_categorie": 28,
                    "resultat_ffme": "1er / 28",
                    "performance": "Finale (Top)"
                },
                {
                    "nom": "DUPONT",
                    "prenom": "Jean",
                    "num_licence": "123456",
                    "categorie": "U17 Homme",
                    "classement": "2",
                    "total_categorie": 34,
                    "resultat_ffme": "2e / 34",
                    "performance": "Finale 4t 4z"
                }
            ]
        }]

        html = results_email_html(comp_data, [])
        self.assertIn("Open Régional Bloc Jonage", html)
        self.assertIn("BULAND", html)
        self.assertIn("DUPONT", html)
        self.assertIn("🥇", html)  # Médaille d'or 1er
        self.assertIn("🥈", html)  # Médaille d'argent 2e
        self.assertIn("https://mycompet.ffme.fr/resultat/resultat_13660", html)
        self.assertTrue("batch quotidien ALJ Escalade" in html)

    def test_invalid_notification_address_sends_nothing(self):
        """Une adresse de notification invalide n'interrompt pas le batch : pas d'envoi, False."""
        item = {"id": "10", "nom": "Open", "date": "2026-10-10", "lieu": "", "url": "", "athletes": []}
        with patch("services.competitions.results_batch.EmailSender.send_email") as send_email:
            sent = CompetitionResultsBatchService.send_notification_email([item], to_email="adresse_invalide")
        self.assertFalse(sent)
        send_email.assert_not_called()


def test_apply_rankings_matches_name_without_accents_or_hyphens():
    participants = [{"nom": "Lefèvre", "prenom": "Zoé-Anne", "num_licence": ""}, {"nom": "Autre", "prenom": "Grimpeur"}]
    scraped = [{"nom": "LEFEVRE", "prenom": "Zoe Anne", "licence": "", "classement": "3", "total_categorie": 12,
                "categorie": "U13 Femme"}]
    athletes = apply_rankings(participants, scraped, "2026-10-26T07:00:00")
    assert [a["classement"] for a in athletes] == ["3"]
    assert participants[0]["resultat_ffme"] == "3 / 12"
    assert "classement" not in participants[1]


if __name__ == "__main__":
    unittest.main()
