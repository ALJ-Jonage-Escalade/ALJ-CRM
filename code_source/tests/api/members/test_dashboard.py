"""GET /api/dashboard: the membership campaign's registrations, read with the same campaign setting and the same item
mapper as the members import (HelloAsso mocked, fake data only)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from support.api_case import ApiTestCase
from support.helloasso_items import ha_item
from support.member_db import MemberDbTestCase

from infrastructure.firestore.app_settings import AppSettingsRepository


class TestMembershipDashboard(MemberDbTestCase, ApiTestCase):

    def dashboard(self, items: list[dict[str, Any]]) -> tuple[dict[str, Any], list[tuple[str, str]]]:  # Any: JSON
        read: list[tuple[str, str]] = []

        def get_items(form_type: str, slug: str) -> list[dict[str, Any]]:
            read.append((form_type, slug))
            return items

        campaigns = [{"formSlug": "adhesions-reglage-2026-2027", "formType": "Membership", "title": "Adhésions"}]
        with patch("infrastructure.helloasso.api.get_campaigns", return_value=campaigns), \
                patch("infrastructure.helloasso.api.get_items", side_effect=get_items):
            response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), read

    def test_the_dashboard_reads_the_campaign_setting_and_the_shared_mapper(self) -> None:
        AppSettingsRepository.save("HELLOASSO_MEMBERSHIP_CAMPAIGN", "adhesions-reglage-2026-2027")
        luna = ha_item(2, "LOVEGOOD", "Luna", customFields=[{"name": "Ville", "value": "Meyzieu"}, {"name": "Code postal", "answer": "69330"}],
                       options=[{"name": "Assurance Base +", "amount": 1100}])
        donation = dict(ha_item(3, "MALFOY", "Draco"), type="Donation")

        body, read = self.dashboard([ha_item(1, "WEASLEY", "Ginny"), luna, donation])

        self.assertEqual(read, [("Membership", "adhesions-reglage-2026-2027")])
        self.assertEqual(body["total_inscrits"], 2)
        participant = next(p for p in body["participants"] if p["user_lastName"] == "LOVEGOOD")
        self.assertEqual((participant["city"], participant["zip"], participant["full_address"]), ("MEYZIEU", "69330", "MEYZIEU, 69330, France"))
        self.assertEqual((participant["opt_Assurance Base +"], participant["opt_Montant Assurance Base +"]), ("Oui", 11.0))
        self.assertEqual(body["tariffs"], [{"name": "Loisir collège", "count": 2}])

    def test_an_unknown_campaign_is_reported(self) -> None:
        AppSettingsRepository.save("HELLOASSO_MEMBERSHIP_CAMPAIGN", "adhesions-autre-2026-2027")

        body, read = self.dashboard([])

        self.assertEqual((body, read), ({"error": "Campagne introuvable"}, []))
