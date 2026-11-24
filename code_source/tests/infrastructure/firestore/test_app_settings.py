"""AppSettingsRepository: Firestore `app_settings`."""

from infrastructure.firestore.app_settings import AppSettingsRepository as Settings
from support.fake_firestore import FirestoreRepoTestCase


class TestAppSettings(FirestoreRepoTestCase):
    def test_settings_roundtrip(self):
        self.assertEqual(Settings.get("HELLOASSO_ANNUAL_CAMPAIGN"), "")
        Settings.save("HELLOASSO_ANNUAL_CAMPAIGN", "competition-saison-2026")
        self.assertEqual(Settings.get("HELLOASSO_ANNUAL_CAMPAIGN"), "competition-saison-2026")
        Settings.save("HELLOASSO_ANNUAL_CAMPAIGN", "")
        self.assertEqual(Settings.get("HELLOASSO_ANNUAL_CAMPAIGN"), "")

    def test_blank_value_returns_default(self):
        Settings.save("whatsapp_template", "   ")
        self.assertIsNone(Settings.get("whatsapp_template", None))
        self.assertEqual(Settings.get("missing", "fallback"), "fallback")
