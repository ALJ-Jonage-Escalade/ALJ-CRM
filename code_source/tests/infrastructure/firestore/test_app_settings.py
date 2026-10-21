"""AppSettingsRepository: Firestore `app_settings`, with the former crm_app_settings values as fallback."""

from infrastructure.firestore.app_settings import COLLECTION, LEGACY_COLLECTION, AppSettingsRepository as Settings
from infrastructure.firestore.cloud_database import doc_id_for
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

    def test_legacy_value_read_once_and_copied(self):
        self.fake.upsert_document(LEGACY_COLLECTION, doc_id_for(["whatsapp_template"]),
                                  {"key": "whatsapp_template", "value": "Rejoignez le groupe", "_modified_at": "x"})
        self.assertEqual(Settings.get("whatsapp_template"), "Rejoignez le groupe")
        self.assertEqual(self.fake.store[COLLECTION]["whatsapp_template"]["value"], "Rejoignez le groupe")

        # The new collection wins from now on, even once cleared
        Settings.save("whatsapp_template", "")
        self.assertEqual(Settings.get("whatsapp_template", None), None)

    def test_deleted_legacy_value_ignored(self):
        self.fake.upsert_document(LEGACY_COLLECTION, doc_id_for(["RESULTATS_NOTIFICATION_EMAIL"]),
                                  {"key": "RESULTATS_NOTIFICATION_EMAIL", "value": "old@club.fr", "_deleted": True})
        self.assertEqual(Settings.get("RESULTATS_NOTIFICATION_EMAIL"), "")
        self.assertNotIn("RESULTATS_NOTIFICATION_EMAIL", self.fake.store.get(COLLECTION, {}))
