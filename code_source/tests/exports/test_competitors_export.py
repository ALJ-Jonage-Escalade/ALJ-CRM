import unittest
from exports.competitors_excel import export_competitors_excel, payment_label
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
                    "categorie": "U17",
                    "sex": "H",
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
                    "categorie": "VETERAN_1",
                    "sex": "F",
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
        import io

        import openpyxl
        cells = [c.value for row in openpyxl.load_workbook(io.BytesIO(data)).active.iter_rows() for c in row]
        self.assertIn("U17 H", cells)

    def test_export_html_and_pdf(self):
        html_code = generate_competitors_html(self.comp)
        self.assertIn("ALJ Escalade", html_code)
        self.assertIn("POTTER", html_code)
        self.assertIn("GRANGER", html_code)
        self.assertIn("777888", html_code)
        self.assertIn("U17 H", html_code)
        self.assertIn("Vétéran 1 F", html_code)

        pdf_bytes = export_competitors_pdf(self.comp)
        self.assertTrue(len(pdf_bytes) > 0)

    def test_payment_label_uses_domain_labels(self):
        cases = [
            ({"statut_paiement": "paye", "montant_paye": 15.5}, "Payé (15,50 €)"),
            ({"statut_paiement": "paye", "montant_paye": 15.0}, "Payé (15 €)"),
            ({"statut_paiement": "en_attente"}, "En attente"),
            ({"statut_paiement": "annule_perdu", "montant_paye": 0}, "Annulé — perdu"),
            ({"statut_paiement": "annule_reporte"}, "Annulé — report"),
            ({}, "Non invité"),
        ]
        for participant, expected in cases:
            with self.subTest(participant=participant):
                self.assertEqual(payment_label(participant), expected)


if __name__ == "__main__":
    unittest.main()
