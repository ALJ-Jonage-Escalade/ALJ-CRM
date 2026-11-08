import os
import sys
import unittest

# Ajustement du chemin pour importer les modules depuis 'src'
_test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(os.path.dirname(_test_dir), "src") if os.path.basename(_test_dir) == "tests" else _test_dir
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from domain.validators import validate_amount, validate_email
from domain.constants import get_active_season

class TestDomainLot1(unittest.TestCase):


    def test_validate_amount(self):
        """Vérifie la robustesse du validateur de montant financier."""
        self.assertEqual(validate_amount(246.50), 246.50)
        self.assertEqual(validate_amount("246,50"), 246.50)
        self.assertEqual(validate_amount(" 246.50 € "), 246.50)
        self.assertEqual(validate_amount("246 500,50 EUR"), 246500.50)
        self.assertEqual(validate_amount(""), 0.0)
        self.assertEqual(validate_amount(None), 0.0)

        with self.assertRaises(ValueError):
            validate_amount("invalide-123")

    def test_validate_email(self):
        """Vérifie la robustesse du validateur d'e-mail."""
        self.assertEqual(validate_email("test@domain.com"), "test@domain.com")
        self.assertEqual(validate_email("  TEST@DOMAIN.COM  "), "test@domain.com")
        self.assertEqual(validate_email(""), "")
        self.assertEqual(validate_email(None), "")

        with self.assertRaises(ValueError):
            validate_email("invalide_email_sans_at")

    def test_get_active_season(self):
        """Vérifie la configuration dynamique des saisons."""
        season = get_active_season()
        self.assertIsInstance(season, str)
        self.assertGreater(len(season), 0)

if __name__ == "__main__":
    unittest.main()
