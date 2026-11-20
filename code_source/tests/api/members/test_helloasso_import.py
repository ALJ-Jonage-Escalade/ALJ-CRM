"""Import of the HelloAsso membership campaign (api/members/helloasso_import.py): campaign setting, preview and import,
over a temporary member database and an in-memory Firestore, HelloAsso mocked (fake data only)."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from support.api_case import ApiTestCase
from support.helloasso_items import ha_item, ha_refunded_payment
from support.member_db import MemberDbTestCase

from infrastructure.helloasso.api import HelloAssoApiError
from infrastructure.security.api_auth import Role, required_role
from infrastructure.sqlite.connection import SqliteDatabase

CAMPAIGN = "adhesion-escalade-2026-2027-amicale-laique-escalade-2"
PREVIEW = "/api/helloasso/memberships/preview"


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
        for method, path in (("POST", PREVIEW), ("POST", "/api/helloasso/memberships/import"),
                             ("GET", "/api/helloasso/memberships/last-sync")):
            with self.subTest(path=path):
                self.assertEqual(required_role(method, path), Role.ADMIN)

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

    def test_preview_rows_list_the_problems_of_their_data(self) -> None:
        self.items = [ha_item(1, "WEASLEY", "Ginny"), ha_item(2, "LOVEGOOD", "Luna", birth_date="01/01/1026")]

        rows = {row["item_id"]: row for row in self.client.post(PREVIEW).json()["rows"]}

        self.assertEqual(rows[1]["issues"], [])
        self.assertEqual((rows[2]["bucket"], rows[2]["can_create"], rows[2]["birth_date"]), ("to_review", False, "01/01/1026"))
        [issue] = rows[2]["issues"]
        self.assertEqual((issue["field"], issue["code"], issue["blocking"]), ("birth_date", "too_old", True))
        self.assertIn("01/01/1026", issue["message"])

    def test_preview_reads_the_environment_then_the_default_campaign_of_the_season(self) -> None:
        self.client.post(PREVIEW)
        with patch.dict(os.environ, {"CAMPAIGN_SLUG": "https://www.helloasso.com/associations/alj/adhesions/adhesions-env-2026-2027"}):
            self.client.post(PREVIEW)

        self.assertEqual(self.fetched, [("Membership", CAMPAIGN), ("Membership", "adhesions-env-2026-2027")])

    def test_preview_reads_the_campaign_chosen_for_this_sync_without_saving_it(self) -> None:
        response = self.client.post(PREVIEW, json={"campaign": "adhesions-bis-2026-2027"})
        self.client.post(PREVIEW, json={"campaign": " "})

        self.assertEqual(response.json()["campaign"], "adhesions-bis-2026-2027")
        self.assertEqual(self.fetched, [("Membership", "adhesions-bis-2026-2027"), ("Membership", CAMPAIGN)])

    def test_a_campaign_of_another_season_blocks_the_whole_preview(self) -> None:
        self.items = [ha_item(1, "WEASLEY", "Ginny")]

        with patch.dict(os.environ, {"CAMPAIGN_SLUG": "adhesion-escalade-2025-2026"}):
            body = self.client.post(PREVIEW).json()

        self.assertIn("2026-2027", body["blocked_reason"])
        self.assertEqual([row["bucket"] for row in body["rows"]], ["blocked"])

    def test_an_unreadable_campaign_is_refused(self) -> None:
        with patch.dict(os.environ, {"CAMPAIGN_SLUG": "https://www.helloasso.com/associations"}):
            response = self.client.post(PREVIEW)

        self.assertEqual((response.status_code, response.json()["code"]), (400, "invalid_campaign"))
        self.assertEqual(self.fetched, [])

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


IMPORT = "/api/helloasso/memberships/import"


class TestMembershipImport(HelloAssoImportTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.items = [ha_item(1, "WEASLEY", "Ginny"), ha_item(2, "LOVEGOOD", "Luna", birth_date="13/02/2012")]

    def test_preview_then_import_creates_the_checked_new_members_only(self) -> None:
        preview = self.client.post(PREVIEW).json()
        self.assertEqual([row["bucket"] for row in preview["rows"]], ["new", "new"])

        with patch("smtplib.SMTP") as smtp, patch("smtplib.SMTP_SSL") as smtp_ssl, \
                patch("infrastructure.mail.sender.EmailSender.send_email") as send_email:
            response = self.client.post(IMPORT, json={"season": "2026-2027", "decisions": {
                "1": {"bucket": "new", "choice": "import"}, "2": {"bucket": "new", "choice": "skip"}}})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["season"], "2026-2027")
        [created] = body["created"]
        self.assertEqual((created["item_id"], created["last_name"], created["first_name"]), (1, "WEASLEY", "Ginny"))
        self.assertEqual(body["counts"], {"created": 1, "renewed": 0, "updated": 0, "attached": 0, "skipped": 1})
        self.assertEqual((self.count("users"), self.count("orders"), self.count("purchases"), self.count("purchase_options")),
                         (1, 1, 1, 1))
        conn = SqliteDatabase.get_connection()
        try:
            purchase = conn.execute("SELECT id, user_id, helloasso_item_id FROM purchases").fetchone()
        finally:
            conn.close()
        self.assertEqual((created["user_id"], created["purchase_id"], purchase["helloasso_item_id"]),
                         (purchase["user_id"], purchase["id"], 1))
        smtp.assert_not_called()
        smtp_ssl.assert_not_called()
        send_email.assert_not_called()

    def test_the_import_reads_the_campaign_chosen_for_this_sync_and_records_it(self) -> None:
        response = self.client.post(IMPORT, json={"season": "2026-2027", "campaign": "adhesions-bis-2026-2027",
                                                  "decisions": {"1": {"bucket": "new", "choice": "import"}}})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.fetched, [("Membership", "adhesions-bis-2026-2027")])
        last = self.client.get("/api/helloasso/memberships/last-sync").json()["last_sync"]
        self.assertEqual(last["campaign"], "adhesions-bis-2026-2027")

    def test_import_of_another_season_or_a_blocked_campaign_is_refused(self) -> None:
        decisions = {"1": {"bucket": "new", "choice": "import"}}
        other_season = self.client.post(IMPORT, json={"season": "2025-2026", "decisions": decisions})
        self.assertEqual((other_season.status_code, other_season.json()["code"]), (409, "stale_decisions"))

        with patch.dict(os.environ, {"CAMPAIGN_SLUG": "adhesion-escalade-2025-2026"}):
            blocked = self.client.post(IMPORT, json={"season": "2026-2027", "decisions": decisions})

        self.assertEqual((blocked.status_code, blocked.json()["code"]), (409, "campaign_blocked"))
        self.assertIn("2026-2027", blocked.json()["message"])
        self.assertEqual(self.count("users"), 0)


class TestMembershipRerunsAndRenewals(HelloAssoImportTestCase):

    def import_all(self) -> dict[str, Any]:  # Any: JSON body
        preview = self.client.post(PREVIEW).json()
        decisions = {str(row["item_id"]): {"bucket": row["bucket"], "choice": "import"}
                     for row in preview["rows"] if row["bucket"] in ("new", "renewal")}
        response = self.client.post(IMPORT, json={"season": preview["season"], "decisions": decisions})
        self.assertEqual(response.status_code, 200, response.text)
        return dict(response.json())

    def test_running_the_import_twice_creates_no_duplicate(self) -> None:
        self.items = [ha_item(1, "WEASLEY", "Ginny"), ha_item(2, "LOVEGOOD", "Luna", birth_date="13/02/2012")]
        self.import_all()

        second = self.client.post(PREVIEW).json()
        self.import_all()

        self.assertEqual(second["counts"]["already_imported"], 2)
        self.assertEqual((self.count("users"), self.count("orders"), self.count("purchases")), (2, 2, 2))

    def test_a_returning_member_gets_the_new_season_on_their_record(self) -> None:
        self.seed("ORD-OLD", "Ginny", "WEASLEY", "Loisir collège", season="2025-2026",
                  **{"champ_Date de naissance de l'adhérent": "2013-08-11", "champ_Téléphone ": "0600000000"})
        self.items = [ha_item(1, "Weasley", "Ginny")]

        result = self.import_all()

        [renewed] = result["renewed"]
        self.assertEqual((renewed["last_name"], renewed["first_name"]), ("Weasley", "Ginny"))
        self.assertEqual(result["counts"], {"created": 0, "renewed": 1, "updated": 0, "attached": 0, "skipped": 0})
        self.assertEqual((self.count("users"), self.count("purchases")), (1, 2))

class TestMembershipsToReview(HelloAssoImportTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.seed("ORD-OLD", "Ginny", "WEASLEY", "Loisir collège", season="2025-2026",
                  **{"champ_Date de naissance de l'adhérent": "2013-09-11"})
        conn = SqliteDatabase.get_connection()
        try:
            self.ginny = int(conn.execute("SELECT id FROM users").fetchone()[0])
        finally:
            conn.close()
        self.items = [ha_item(1, "WEASLEY", "Ginny", birth_date="11/08/2013")]

    def test_a_row_to_review_lists_its_candidates(self) -> None:
        [row] = self.client.post(PREVIEW).json()["rows"]

        self.assertEqual(row["bucket"], "to_review")
        self.assertTrue(row["can_create"])
        self.assertEqual(row["candidates"], [{"user_id": self.ginny, "last_name": "WEASLEY", "first_name": "Ginny",
                                              "birth_date": "2013-09-11", "licence": ""}])

    def test_linking_a_row_to_review_attaches_it_to_the_candidate(self) -> None:
        response = self.client.post(IMPORT, json={"season": "2026-2027", "decisions": {
            "1": {"bucket": "to_review", "choice": f"link:{self.ginny}"}}})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([member["user_id"] for member in response.json()["renewed"]], [self.ginny])
        self.assertEqual((self.count("users"), self.count("purchases")), (1, 2))

    def test_creating_from_a_row_to_review_makes_a_new_member(self) -> None:
        response = self.client.post(IMPORT, json={"season": "2026-2027", "decisions": {"1": {"bucket": "to_review", "choice": "create"}}})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["created"]), 1)
        self.assertEqual((self.count("users"), self.count("purchases")), (2, 2))

class TestMembershipsChangedOnHelloAsso(HelloAssoImportTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.items = [ha_item(1, "WEASLEY", "Ginny")]
        self.client.post(IMPORT, json={"season": "2026-2027", "decisions": {"1": {"bucket": "new", "choice": "import"}}})

    def purchase(self) -> dict[str, Any]:  # Any: SQLite values
        conn = SqliteDatabase.get_connection()
        try:
            return dict(conn.execute("SELECT status, amount, helloasso_status FROM purchases").fetchone())
        finally:
            conn.close()

    def test_a_refund_on_helloasso_is_proposed_and_applied(self) -> None:
        self.items = [ha_item(1, "WEASLEY", "Ginny", payments=[ha_refunded_payment()])]

        [row] = self.client.post(PREVIEW).json()["rows"]
        result = self.client.post(IMPORT, json={"season": "2026-2027", "decisions": {"1": {"bucket": "updated", "choice": "import"}}}).json()

        self.assertEqual(row["bucket"], "updated")
        self.assertEqual(row["changes"], [{"field": "status", "crm": "Processed", "before": "Processed", "after": "Refunded"}])
        self.assertEqual((row["payment_date"], row["refund_date"]), ("2026-09-01T10:05:00+02:00", "2026-10-14T09:30:00+02:00"))
        self.assertEqual(result["counts"]["updated"], 1)
        self.assertEqual([m["last_name"] for m in result["updated"]], ["WEASLEY"])
        self.assertEqual(self.purchase(), {"status": "Refunded", "amount": 150.0, "helloasso_status": "Refunded"})

    def test_a_status_changed_in_the_crm_is_kept_until_helloasso_changes(self) -> None:
        self.client.post("/api/members/update", json={"user_id": 1, "fields": {"status": "Terminé"}})
        self.assertEqual(self.purchase()["status"], "Terminé")

        self.assertEqual(self.client.post(PREVIEW).json()["rows"][0]["bucket"], "already_imported")
        self.items = [ha_item(1, "WEASLEY", "Ginny", payments=[ha_refunded_payment()])]
        [row] = self.client.post(PREVIEW).json()["rows"]

        self.assertEqual(row["bucket"], "to_review")
        self.assertEqual(row["changes"], [{"field": "status", "crm": "Terminé", "before": "Processed", "after": "Refunded"}])


class TestMembershipImportHistory(HelloAssoImportTestCase):

    def test_each_import_leaves_one_history_entry_and_the_last_sync(self) -> None:
        self.assertEqual(self.client.get("/api/helloasso/memberships/last-sync").json(), {"last_sync": None})
        self.items = [ha_item(1, "WEASLEY", "Ginny"), ha_item(2, "LOVEGOOD", "Luna", birth_date="")]

        result = self.client.post(IMPORT, json={"season": "2026-2027", "decisions": {"1": {"bucket": "new", "choice": "import"}}}).json()

        history = self.fake.store["helloasso_membership_imports"]
        self.assertEqual(list(history), [result["history_id"]])
        entry = history[result["history_id"]]
        self.assertEqual((entry["author"], entry["season"], entry["campaign"]), ("serveur local", "2026-2027", CAMPAIGN))
        self.assertEqual(entry["counts"], {"already_imported": 0, "new": 1, "renewal": 0, "updated": 0, "to_review": 1, "blocked": 0})
        self.assertEqual(entry["items"], [{"item_id": 1, "bucket": "new", "decision": "import", "action": "create"},
                                          {"item_id": 2, "bucket": "to_review", "decision": "skip", "action": ""}])
        last = self.client.get("/api/helloasso/memberships/last-sync").json()["last_sync"]
        self.assertEqual((last["at"], last["author"]), (entry["at"], "serveur local"))


class TestMembershipAttachedByHand(HelloAssoImportTestCase):
    """A parent registered their child under their own name: the admin creates the child by hand, then attaches the
    registration to them."""

    def setUp(self) -> None:
        super().setUp()
        self.items = [ha_item(1, "WEASLEY", "Molly", birth_date="30/10/1950")]
        created = self.client.post("/api/members/create", json={"fields": {
            "last_name": "WEASLEY", "first_name": "Ginny", "birth_date": "2013-08-11", "tarif_name": "Loisir collège"}})
        self.assertEqual(created.status_code, 200, created.text)
        conn = SqliteDatabase.get_connection()
        try:
            self.ginny = int(conn.execute("SELECT id FROM users").fetchone()[0])
        finally:
            conn.close()

    def attach(self, comment: str) -> Any:  # Any: the HTTP response
        return self.client.post(IMPORT, json={"season": "2026-2027", "decisions": {
            "1": {"bucket": "new", "choice": f"attach:{self.ginny}", "comment": comment}}})

    def test_the_registration_takes_over_the_manual_membership_and_is_recognised_next_time(self) -> None:
        response = self.attach("Inscrite par sa mère")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        [attached] = body["attached"]
        self.assertEqual((attached["user_id"], attached["last_name"], attached["first_name"]), (self.ginny, "WEASLEY", "Ginny"))
        self.assertEqual(body["counts"], {"created": 0, "renewed": 0, "updated": 0, "attached": 1, "skipped": 0})
        self.assertEqual((self.count("users"), self.count("orders"), self.count("purchases")), (1, 1, 1))
        [entry] = self.fake.store["helloasso_membership_imports"].values()
        self.assertEqual(entry["items"], [{"item_id": 1, "bucket": "new", "decision": f"attach:{self.ginny}", "action": "assign",
                                           "comment": "Inscrite par sa mère"}])

        [row] = self.client.post(PREVIEW).json()["rows"]
        self.assertEqual(row["bucket"], "already_imported")

    def test_an_attach_without_comment_is_refused(self) -> None:
        response = self.attach(" ")

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("commentaire", response.json()["message"])
        self.assertEqual(self.count("purchases"), 1)

    def test_the_preview_lists_every_member_and_their_membership_this_season(self) -> None:
        preview = self.client.post(PREVIEW).json()

        self.assertEqual(preview["members"], [{"user_id": self.ginny, "last_name": "WEASLEY", "first_name": "Ginny",
                                               "birth_date": "2013-08-11", "licence": "", "membership": "manual"}])

    def test_an_attached_registration_shows_the_member_next_time(self) -> None:
        self.attach("Inscrite par sa mère")

        [row] = self.client.post(PREVIEW).json()["rows"]

        self.assertEqual(row["attached_to"], {"user_id": self.ginny, "last_name": "WEASLEY", "first_name": "Ginny",
                                              "birth_date": "2013-08-11", "licence": ""})
        self.assertIn("rattachée à WEASLEY Ginny", row["reason"])
