"""Club keys (Outils › Clés, plans/club-keys.md): keys of the climbing wall, who holds them, their history.
Temporary member database, auth off (roles: required_role and the route inventory)."""

from __future__ import annotations

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from support.member_db import MemberDbTestCase

import server
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.members import MemberRepository


class KeysTestCase(MemberDbTestCase):

    def setUp(self) -> None:
        super().setUp()
        env = patch.dict(os.environ, {"ALJ_API_AUTH": "off"})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(server.app)

    def add_key(self, code: str) -> dict:
        r = self.client.post("/api/keys", json={"code": code})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def keys(self) -> list:
        r = self.client.get("/api/keys")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def key(self, key_id: int) -> dict:
        return next(k for k in self.keys() if k["id"] == key_id)

    def member(self, ref: str, first_name: str, last_name: str, season: str = "2026-2027", **extra: str) -> int:
        """A member of the season (2026-2027 is the active one); their user id."""
        self.seed(ref, first_name, last_name, "Loisir", season=season, **extra)
        rows = MemberRepository.list_member_rows(season)
        return next(r["user_id"] for r in rows if r["first_name"] == first_name and r["last_name"] == last_name)

    def assign(self, key_id: int, user_id: int, given_on: str = "2026-09-12", comment: str = "") -> object:
        return self.client.post(f"/api/keys/{key_id}/assignments", json={"user_id": user_id, "given_on": given_on, "comment": comment})

    def give_back(self, key_id: int, returned_on: str = "2027-06-30", comment: str = "") -> object:
        return self.client.post(f"/api/keys/{key_id}/return", json={"returned_on": returned_on, "comment": comment})

    def activate_season(self, name: str) -> None:
        conn = SqliteDatabase.get_connection()
        try:
            conn.execute("UPDATE seasons SET is_active = 0")
            conn.execute("INSERT INTO seasons (name, is_active) VALUES (?, 1)"
                         " ON CONFLICT(name) DO UPDATE SET is_active = 1", (name,))
            conn.commit()
        finally:
            conn.close()


class TestAddKey(KeysTestCase):

    def test_added_key_is_listed_available(self) -> None:
        self.add_key("12")
        self.assertEqual([(k["code"], k["status"]) for k in self.keys()], [("12", "available")])

    def test_code_is_trimmed(self) -> None:
        self.assertEqual(self.add_key("  A7 ")["code"], "A7")

    def test_duplicate_code_whatever_its_case_is_refused(self) -> None:
        self.add_key("a7")
        for code in ("a7", "A7", " A7 "):
            with self.subTest(code=code):
                r = self.client.post("/api/keys", json={"code": code})
                self.assertEqual(r.status_code, 409, r.text)
                self.assertEqual(r.json()["code"], "duplicate_code")
        self.assertEqual(len(self.keys()), 1)

    def test_empty_code_is_refused(self) -> None:
        for code in ("", "   "):
            with self.subTest(code=code):
                self.assertEqual(self.client.post("/api/keys", json={"code": code}).status_code, 422)


class TestKeyAccess(KeysTestCase):

    def test_coaches_read_admins_write(self) -> None:
        from infrastructure.security.api_auth import Role, required_role
        self.assertEqual(required_role("GET", "/api/keys"), Role.COACH)
        for method, path in (("POST", "/api/keys"), ("PATCH", "/api/keys/1"), ("POST", "/api/keys/1/archive"),
                             ("PATCH", "/api/key-assignments/1"), ("DELETE", "/api/key-assignments/1")):
            with self.subTest(method=method, path=path):
                self.assertEqual(required_role(method, path), Role.ADMIN)


class TestAssignKey(KeysTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.key_id = self.add_key("12")["id"]
        self.harry = self.member("1", "Harry", "POTTER")

    def test_assigned_key_shows_its_holder(self) -> None:
        r = self.assign(self.key_id, self.harry, "2026-09-12", "Remise au forum")
        self.assertEqual(r.status_code, 200, r.text)
        key = self.key(self.key_id)
        self.assertEqual(key["status"], "assigned")
        self.assertEqual(key["holder"], {"user_id": self.harry, "last_name": "POTTER", "first_name": "Harry",
                                         "given_on": "2026-09-12", "comment": "Remise au forum", "member_this_season": True,
                                         "season": "2026-2027"})

    def test_available_key_has_no_holder(self) -> None:
        self.assertIsNone(self.key(self.key_id)["holder"])

    def test_a_held_key_cannot_be_assigned_again(self) -> None:
        self.assign(self.key_id, self.harry)
        ron = self.member("2", "Ron", "WEASLEY")
        r = self.assign(self.key_id, ron)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "key_not_available"))

    def test_a_member_holds_one_key_only(self) -> None:
        self.assign(self.key_id, self.harry)
        other = self.add_key("13")["id"]
        r = self.assign(other, self.harry)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "member_has_key"))
        self.assertIn("12", r.json()["message"])

    def test_only_members_of_the_active_season(self) -> None:
        former = self.member("3", "Cedric", "DIGGORY", season="2025-2026")
        r = self.assign(self.key_id, former)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "not_a_member"))

    def test_a_cancelled_membership_does_not_count(self) -> None:
        cancelled = self.member("4", "Draco", "MALFOY", status="Canceled")
        r = self.assign(self.key_id, cancelled)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "not_a_member"))

    def test_unknown_key(self) -> None:
        self.assertEqual(self.assign(999, self.harry).status_code, 404)

    def test_holder_who_did_not_renew_is_flagged(self) -> None:
        self.assign(self.key_id, self.harry)
        self.activate_season("2027-2028")
        holder = self.key(self.key_id)["holder"]
        self.assertFalse(holder["member_this_season"])
        self.assertEqual(holder["season"], "2026-2027")  # their record, linked from the page, is in their last season


class TestReturnKey(KeysTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.key_id = self.add_key("12")["id"]
        self.harry = self.member("1", "Harry", "POTTER")
        self.assign(self.key_id, self.harry, "2026-09-12")

    def test_returned_key_is_available_again(self) -> None:
        r = self.give_back(self.key_id, "2027-06-30", "Fin de saison")
        self.assertEqual(r.status_code, 200, r.text)
        key = self.key(self.key_id)
        self.assertEqual((key["status"], key["holder"]), ("available", None))

    def test_returned_key_can_go_to_someone_else_and_back(self) -> None:
        self.give_back(self.key_id)
        ron = self.member("2", "Ron", "WEASLEY")
        self.assertEqual(self.assign(self.key_id, ron, "2027-07-01").status_code, 200)
        self.give_back(self.key_id, "2027-07-02")
        self.assertEqual(self.assign(self.key_id, self.harry, "2027-07-03").status_code, 200)

    def test_return_before_it_was_given_is_refused(self) -> None:
        r = self.give_back(self.key_id, "2026-09-11")
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(self.key(self.key_id)["status"], "assigned")

    def test_a_key_nobody_holds_cannot_be_returned(self) -> None:
        self.give_back(self.key_id)
        self.assertEqual(self.give_back(self.key_id).status_code, 409)
