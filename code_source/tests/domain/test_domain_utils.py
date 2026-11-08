import unittest
import sys
import os

# Ajustement du chemin d'import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))
from domain.utils import normalize_string, normalize_name, normalize_key_part, clean_city_name, is_helloasso_url

class TestDomainUtils(unittest.TestCase):
    def test_is_helloasso_url(self):
        cases = {
            "https://www.helloasso.com/associations/alj/evenements/x": True,
            "www.helloasso.com/associations/alj/evenements/x": True,
            "HTTPS://HelloAsso.com/associations/alj": True,
            "adhesion-escalade-2026-2027-amicale-laique-escalade-2": False,
            "Event:competition-u11": False,
            "https://evil.example/helloasso.com/associations/alj": False,
            "https://helloasso.com.evil.example/associations/alj": False,
            "https://evilhelloasso.com/associations/alj": False,
            "": False,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(is_helloasso_url(value), expected)

    def test_clean_city_name(self):
        # Variations de Villette d'Anthon
        variations = [
            'Villette D’Anthon', 'Villette D’anthon', 'villette d\'anthon',
            'VILLETTE D ANTHON', 'Villette-d\'Anthon', 'Villette d\'anthon',
            'Villette D Anthon', 'Villette d’Anthon', 'Villette d’anthon',
            'VILLETTE-D\'ANTHON'
        ]
        for var in variations:
            self.assertEqual(clean_city_name(var), "Villette D'Anthon")

        # Cas d'autres villes
        self.assertEqual(clean_city_name("JONAGE"), "Jonage")
        self.assertEqual(clean_city_name("saint-maurice-de-gourdans"), "Saint Maurice De Gourdans")
        self.assertEqual(clean_city_name("D'HUISON-LONGUEVILLE"), "D'Huison Longueville")
        self.assertEqual(clean_city_name(None), "Inconnue")
        self.assertEqual(clean_city_name(float("nan")), "Inconnue")

    def test_normalize_string(self):
        # Accents et majuscules
        self.assertEqual(normalize_string("Hanaé"), "hanae")
        self.assertEqual(normalize_string("André"), "andre")
        self.assertEqual(normalize_string("Céline"), "celine")
        
        # None and NaN values
        self.assertEqual(normalize_string(None), "")
        self.assertEqual(normalize_string(float("nan")), "")
        self.assertEqual(normalize_string(float('nan')), "")
        
        # Espaces superflus
        self.assertEqual(normalize_string("  Jean-Pierre  "), "jean-pierre")

    def test_normalize_name(self):
        # Remplacement des tirets par des espaces et collapse des blancs
        self.assertEqual(normalize_name("Jean-Pierre"), "jean pierre")
        self.assertEqual(normalize_name("  DUPONT   Jean-Marie  "), "dupont jean marie")
        self.assertEqual(normalize_name("Söen-Guilhem"), "soen guilhem")
        
        # None and NaN values
        self.assertEqual(normalize_name(None), "")
        self.assertEqual(normalize_name(float("nan")), "")

    def test_normalize_key_part(self):
        # Retrait des espaces, tirets et deux-points
        self.assertEqual(normalize_key_part("Mercredi"), "mercredi")
        self.assertEqual(normalize_key_part("18h-20h"), "18h20h")
        self.assertEqual(normalize_key_part("20:00"), "2000")
        self.assertEqual(normalize_key_part("Cours-perfectionnement"), "coursperfectionnement")
        
        # None and NaN values
        self.assertEqual(normalize_key_part(None), "")

if __name__ == "__main__":
    unittest.main()
