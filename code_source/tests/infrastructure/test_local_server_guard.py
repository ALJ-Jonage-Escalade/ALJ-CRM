"""
Local (unauthenticated) server protection: the desktop app's API on 127.0.0.1 must not
be usable by a website the user visits (cross-site writes, DNS rebinding, CORS reads).
On Cloud Run (token check enforced) the guard is a no-op.
"""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from infrastructure.security.api_auth import local_request_error

LOCAL = "127.0.0.1:8000"


class TestLocalRequestRules(unittest.TestCase):

    def test_loopback_hosts_allowed(self):
        for host in ("127.0.0.1:8000", "localhost:8080", "localhost", "[::1]:8000"):
            with self.subTest(host=host):
                self.assertIsNone(local_request_error("GET", host, None, None))

    def test_foreign_host_rejected(self):
        """DNS rebinding: evil.example resolved to 127.0.0.1 still carries its own Host."""
        for host in ("evil.example", "evil.example:8000", "127.0.0.1.evil.example"):
            with self.subTest(host=host):
                self.assertIsNotNone(local_request_error("GET", host, None, None))

    def test_cross_site_writes_rejected(self):
        self.assertIsNotNone(local_request_error("POST", LOCAL, "https://evil.example", None))
        self.assertIsNotNone(local_request_error("POST", LOCAL, None, "cross-site"))
        self.assertIsNotNone(local_request_error("DELETE", LOCAL, "null", None))

    def test_same_origin_writes_allowed(self):
        self.assertIsNone(local_request_error("POST", LOCAL, f"http://{LOCAL}", "same-origin"))
        self.assertIsNone(local_request_error("POST", LOCAL, None, None))  # desktop app (no browser)

    def test_cross_site_reads_allowed_without_cors(self):
        """GET is harmless: without CORS headers the foreign page cannot read the response."""
        self.assertIsNone(local_request_error("GET", LOCAL, "https://evil.example", "cross-site"))


class TestServerGuard(unittest.TestCase):

    def setUp(self):
        from server import app
        self.client = TestClient(app)

    def test_no_cors_headers(self):
        resp = self.client.get("/health", headers={"Origin": "https://evil.example", "Host": LOCAL})
        self.assertNotIn("access-control-allow-origin", resp.headers)

    def test_local_mode(self):
        with patch.dict(os.environ, {"ALJ_API_AUTH": "off"}):
            self.assertEqual(self.client.get("/health", headers={"Host": "evil.example"}).status_code, 403)
            # A slot without a group: refused by the route itself (400) once the guard lets the write through
            resp = self.client.post("/api/planning/item", json={"groupe": ""},
                                    headers={"Host": LOCAL, "Origin": "https://evil.example"})
            self.assertEqual(resp.status_code, 403)
            resp = self.client.post("/api/planning/item", json={"groupe": ""},
                                    headers={"Host": LOCAL, "Origin": f"http://{LOCAL}"})
            self.assertEqual(resp.status_code, 400)

    def test_cloud_run_mode_unaffected(self):
        with patch.dict(os.environ, {"ALJ_API_AUTH": "required"}):
            self.assertEqual(self.client.get("/health", headers={"Host": "alj.run.app"}).status_code, 200)


class TestResponseHardening(unittest.TestCase):

    def setUp(self):
        from server import app
        self.client = TestClient(app)

    def test_security_headers(self):
        for path in ("/health", "/bureau/", "/api/web-version"):
            with self.subTest(path=path):
                headers = self.client.get(path).headers
                self.assertEqual(headers["x-content-type-options"], "nosniff")
                self.assertEqual(headers["referrer-policy"], "same-origin")
                self.assertEqual(headers["content-security-policy"], "frame-ancestors 'self'")

    def test_internal_errors_are_generic(self):
        secret_detail = "sqlite3 at /srv/app/data/database.db: no such table"
        with patch("services.communications.email_templates.EmailTemplateRepository.get_email_templates",
                   side_effect=RuntimeError(secret_detail)):
            body = self.client.get("/api/email-templates").json()
        self.assertNotIn(secret_detail, str(body))
        self.assertIn("journaux", body["message"])

    def test_validation_errors_keep_their_message(self):
        with patch.dict(os.environ, {"ALJ_API_AUTH": "off"}):
            with patch("services.members.members.MemberService.find_member",
                       return_value={"first_name": "Harry", "last_name": "Potter", "amount": 0}):
                resp = self.client.post("/api/attestations/preview", json={"purchase_id": 1})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("supérieur à zéro", resp.json()["message"])


if __name__ == "__main__":
    unittest.main()
