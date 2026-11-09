"""Club keys (Outils › Clés, plans/club-keys.md): keys of the climbing wall, who holds them, their history.
Temporary member database, auth off (roles: required_role and the route inventory)."""

from __future__ import annotations

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from support.member_db import MemberDbTestCase

import server


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
