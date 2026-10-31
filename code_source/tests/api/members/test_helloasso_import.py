"""Import of the HelloAsso membership campaign (api/members/helloasso_import.py): campaign setting, preview and import,
over a temporary member database and an in-memory Firestore, HelloAsso mocked (fake data only)."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from support.api_case import ApiTestCase
from support.member_db import MemberDbTestCase

from infrastructure.firestore.app_settings import AppSettingsRepository
from infrastructure.helloasso.api import HelloAssoApiError
from infrastructure.security.api_auth import Role, required_role
from infrastructure.sqlite.connection import SqliteDatabase

CAMPAIGN = "adhesion-escalade-2026-2027-amicale-laique-escalade-2"
PREVIEW = "/api/helloasso/memberships/preview"


def ha_item(item_id: int, last_name: str, first_name: str, birth_date: str = "11/08/2013", **overrides: Any) -> dict[str, Any]:  # Any: HelloAsso JSON
    item: dict[str, Any] = {
        "id": item_id,
        "type": "Membership",
        "state": "Processed",
        "name": "Loisir collège",
        "amount": 15000,
        "order": {"id": 500 + item_id, "date": "2026-09-01T10:00:00+02:00"},
        "user": {"firstName": first_name, "lastName": last_name},
        "payer": {"firstName": "Molly", "lastName": last_name, "email": "parent@terrier.example"},
        "options": [{"name": "Assurance Base", "amount": 0}],
        "customFields": [
            {"name": "Date de naissance de l'adhérent", "answer": birth_date},
            {"name": "Sexe", "answer": "Femme"},
            {"name": "Ville", "answer": "Jonage"},
        ],
    }
    item.update(overrides)
    return item


class HelloAssoImportTestCase(MemberDbTestCase, ApiTestCase):
    """HelloAsso answers `self.items` for the configured campaign."""

    def setUp(self) -> None:
        super().setUp()
        env = patch.dict(os.environ, {"CAMPAIGN_SLUG": ""})
        env.start()
        self.addCleanup(env.stop)
        self.items: list[dict[str, Any]] = []
        self.fetched: list[tuple[str, str]] = []

        def fetch(form_type: str, slug: str) -> list[dict[str, Any]]:
            self.fetched.append((form_type, slug))
            return self.items

        fetch_patch = patch("infrastructure.helloasso.api.fetch_form_items", side_effect=fetch)
        self.fetch_mock = fetch_patch.start()
        self.addCleanup(fetch_patch.stop)

    def count(self, table: str) -> int:
        conn = SqliteDatabase.get_connection()
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608 - table names of the test
        finally:
            conn.close()


class TestMembershipPreview(HelloAssoImportTestCase):

    def test_import_routes_are_admin_only(self) -> None:
        self.assertEqual(required_role("POST", PREVIEW), Role.ADMIN)
        self.assertEqual(required_role("POST", "/api/helloasso/memberships/import"), Role.ADMIN)

    def test_preview_sorts_the_registrations_and_writes_nothing(self) -> None:
        self.items = [ha_item(1, "WEASLEY", "Ginny"), ha_item(2, "LOVEGOOD", "", birth_date="")]

        response = self.client.post(PREVIEW)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["season"], body["campaign"], body["blocked_reason"]), ("2026-2027", CAMPAIGN, None))
        self.assertEqual(body["counts"], {"already_imported": 0, "new": 1, "renewal": 0, "updated": 0, "to_review": 0, "blocked": 1})
        rows = {row["item_id"]: row for row in body["rows"]}
        self.assertEqual((rows[1]["bucket"], rows[1]["last_name"], rows[1]["birth_date"], rows[1]["amount"]),
                         ("new", "WEASLEY", "2013-08-11", 150.0))
        self.assertEqual(rows[2]["bucket"], "blocked")
        self.assertTrue(rows[2]["reason"])
        self.assertEqual((self.count("users"), self.count("orders"), self.count("purchases")), (0, 0, 0))

    def test_preview_reads_the_campaign_setting_then_the_environment_then_the_default(self) -> None:
        self.client.post(PREVIEW)
        with patch.dict(os.environ, {"CAMPAIGN_SLUG": "adhesions-env-2026-2027"}):
            self.client.post(PREVIEW)
            AppSettingsRepository.save("HELLOASSO_MEMBERSHIP_CAMPAIGN",
                                       "https://www.helloasso.com/associations/alj/adhesions/adhesions-reglage-2026-2027")
            self.client.post(PREVIEW)

        self.assertEqual(self.fetched, [("Membership", CAMPAIGN), ("Membership", "adhesions-env-2026-2027"),
                                        ("Membership", "adhesions-reglage-2026-2027")])

    def test_a_campaign_of_another_season_blocks_the_whole_preview(self) -> None:
        AppSettingsRepository.save("HELLOASSO_MEMBERSHIP_CAMPAIGN", "adhesion-escalade-2025-2026")
        self.items = [ha_item(1, "WEASLEY", "Ginny")]

        body = self.client.post(PREVIEW).json()

        self.assertIn("2026-2027", body["blocked_reason"])
        self.assertEqual([row["bucket"] for row in body["rows"]], ["blocked"])

    def test_helloasso_failures_are_explicit_errors(self) -> None:
        for raised, code in ((HelloAssoApiError("Identifiants HelloAsso absents", "helloasso_credentials_missing"),
                              "helloasso_credentials_missing"),
                             (HelloAssoApiError("API HelloAsso injoignable"), "helloasso_unavailable")):
            with self.subTest(code=code):
                self.fetch_mock.side_effect = raised

                response = self.client.post(PREVIEW)

                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json()["code"], code)
                self.assertIn("HelloAsso", response.json()["message"])


class TestMembershipCampaignSetting(HelloAssoImportTestCase):

    def test_campaign_setting_round_trip(self) -> None:
        self.assertEqual(self.client.get("/api/settings/helloasso-membership").json(),
                         {"campaign": "", "resolved": CAMPAIGN, "source": "default"})

        saved = self.client.post("/api/settings/helloasso-membership", json={"campaign": "adhesions-reglage-2026-2027"})

        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.get("/api/settings/helloasso-membership").json(),
                         {"campaign": "adhesions-reglage-2026-2027", "resolved": "adhesions-reglage-2026-2027", "source": "setting"})

    def test_an_unreadable_campaign_is_refused(self) -> None:
        response = self.client.post("/api/settings/helloasso-membership", json={"campaign": "https://www.helloasso.com/associations"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AppSettingsRepository.get("HELLOASSO_MEMBERSHIP_CAMPAIGN"), "")

    def test_saving_the_campaign_is_admin_only(self) -> None:
        self.assertEqual(required_role("POST", "/api/settings/helloasso-membership"), Role.ADMIN)
