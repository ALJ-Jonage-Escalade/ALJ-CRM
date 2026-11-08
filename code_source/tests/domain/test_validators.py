"""domain/validators.py: amounts and e-mail addresses typed in the forms."""

import unittest

from domain.validators import validate_amount, validate_email


class TestValidators(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
