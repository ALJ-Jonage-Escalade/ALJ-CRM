"""Membership campaign shown by Paramètres › Campagne HelloAsso and read by the members import: Firestore setting,
then CAMPAIGN_SLUG, then the seasonal default."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from api.integrations import helloasso_campaigns
from infrastructure.firestore.app_settings import HELLOASSO_MEMBERSHIP_CAMPAIGN, AppSettingsRepository
from infrastructure.firestore.client import FirestoreError
from services.members import helloasso_import
from services.members.helloasso_import import MembershipImportService
from support.fake_firestore import FirestoreRepoTestCase


class TestTargetSlug(FirestoreRepoTestCase):

    def target_slug(self, env_value: str = "") -> str:
        with patch.object(helloasso_import.SecretStore, "get_secret", return_value=env_value), \
                patch.object(MembershipImportService, "active_season", return_value="2026-2027"):
            return helloasso_campaigns.get_target_slug()

    def test_setting_wins_over_env_variable(self) -> None:
        AppSettingsRepository.save(HELLOASSO_MEMBERSHIP_CAMPAIGN, "Membership:adhesion-2026")
        self.assertEqual(self.target_slug("adhesion-env"), "adhesion-2026")

    def test_the_import_reads_the_same_campaign(self) -> None:
        AppSettingsRepository.save(HELLOASSO_MEMBERSHIP_CAMPAIGN, "Membership:adhesion-2026")
        with patch.object(helloasso_import.SecretStore, "get_secret", return_value="adhesion-env"):
            self.assertEqual(MembershipImportService.campaign().slug, "adhesion-2026")

    def test_env_variable_when_no_setting(self) -> None:
        self.assertEqual(self.target_slug("adhesion-env"), "adhesion-env")

    def test_seasonal_default_when_nothing_set(self) -> None:
        self.assertEqual(self.target_slug(), "adhesion-escalade-2026-2027-amicale-laique-escalade-2")

    def test_firestore_unreadable_falls_back_to_env_variable(self) -> None:
        with patch.object(AppSettingsRepository, "get", side_effect=FirestoreError("down")):
            self.assertEqual(self.target_slug("adhesion-env"), "adhesion-env")


@pytest.mark.parametrize("value, slug", [
    ("Membership:adhesion-2026", "adhesion-2026"),
    ("adhesion-2026", "adhesion-2026"),
    ("https://www.helloasso.com/associations/club/adhesions/adhesion-2026", "adhesion-2026"),
    ("https://www.helloasso.com/associations/club/adhesions/adhesion-2026/", "adhesion-2026"),
    ("https://www.helloasso.com/associations/club/inconnu/adhesion-2026", "adhesion-2026"),
])
def test_get_target_slug_value_formats(value: str, slug: str) -> None:
    with patch.object(MembershipImportService, "campaign_reference", return_value=value):
        assert helloasso_campaigns.get_target_slug() == slug
