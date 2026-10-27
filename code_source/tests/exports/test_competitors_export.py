import unittest
from exports.competitors_excel import export_competitors_excel
from exports.competitors_pdf import export_competitors_pdf, generate_competitors_html


class TestCompetitorsExport(unittest.TestCase):
    def setUp(self):
        self.comp = {
            "id": 18849,
            "nom": "Championnat départemental de bloc Dordogne et Gironde",
            "date_competition": "2026-10-31",
            "date_fin": "2026-11-01",
            "lieu": "PAREMPUYRE",
            "type": "Bloc",
            "prix": 15.0,
            "participants": [
                {
                    "adherent_id": 1,
                    "nom": "POTTER",
                    "prenom": "Harry",
                    "categorie_ffme": "U17",
                    "surclassement": False,
                    "discipline": "Bloc",
                    "selectionne": True,
                    "statut_paiement": "paye",
                    "montant_paye": 15.0,
                    "date_naissance": "2010-07-31",
                    "num_licence": "777888",
                    "email": "harry.potter@example.com",
                    "phone": "0601020304",
                },
                {
                    "adherent_id": 2,
                    "nom": "GRANGER",
                    "prenom": "Hermione",
                    "categorie_ffme": "U17",
                    "surclassement": True,
                    "discipline": "Bloc",
                    "selectionne": True,
                    "statut_paiement": "en_attente",
                    "montant_paye": 0,
                    "date_naissance": "2009-09-19",
                    "num_licence": "888999",
                    "email": "hermione.granger@example.com",
                    "phone": "0605060708",
                },
            ],
        }

    def test_export_excel(self):
        data = export_competitors_excel(self.comp)
        self.assertTrue(len(data) > 0)
        # Check ZIP / XLSX magic bytes
        self.assertTrue(data.startswith(b"PK\x03\x04"))

    def test_export_html_and_pdf(self):
        html_code = generate_competitors_html(self.comp)
        self.assertIn("ALJ Escalade", html_code)
        self.assertIn("POTTER", html_code)
        self.assertIn("GRANGER", html_code)
        self.assertIn("777888", html_code)

        pdf_bytes = export_competitors_pdf(self.comp)
        self.assertTrue(len(pdf_bytes) > 0)


if __name__ == "__main__":
    unittest.main()
