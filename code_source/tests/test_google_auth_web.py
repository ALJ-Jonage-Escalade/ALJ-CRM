"""Tests unitaires des endpoints de renouvellement et de gestion Google OAuth2 pour l'application web."""
import os
import sys
import json
import base64
import unittest
from unittest.mock import patch, MagicMock

_tests_dir = os.path.dirname(os.path.abspath(__file__))
_code_root = os.path.dirname(_tests_dir)
_src_dir = os.path.join(_code_root, "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from fastapi.testclient import TestClient
from server import app

XSS = '"><img src=x onerror=alert(1)>'


class TestGoogleAuthWeb(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    @patch("infrastructure.security.secret_store.SecretStore.get_secret")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_access_token")
    def test_status_disconnected(self, mock_get_tok, mock_creds, mock_secret):
        mock_creds.return_value = (None, None)
        mock_secret.return_value = None
        resp = self.client.get("/api/auth/google/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "disconnected")
        self.assertFalse(data["valid"])
        self.assertFalse(data["configured"])

    @patch("infrastructure.security.secret_store.SecretStore.get_secret")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_access_token")
    def test_status_expired(self, mock_get_tok, mock_creds, mock_secret):
        mock_creds.return_value = ("mock_cid", "mock_sec")
        def fake_secret(k):
            if k == "GMAIL_REFRESH_TOKEN":
                return "old_revoked_token"
            if k == "GMAIL_USER_EMAIL":
                return "test@alj-escalade.fr"
            return None
        mock_secret.side_effect = fake_secret
        mock_get_tok.side_effect = Exception("400 - invalid_grant")

        resp = self.client.get("/api/auth/google/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "expired")
        self.assertFalse(data["valid"])
        self.assertTrue(data["configured"])
        self.assertNotIn("invalid_grant", data["error"])  # Google's detail stays in the server log
        self.assertIn("journaux", data["error"])

    @patch("infrastructure.security.secret_store.SecretStore.get_secret")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_access_token")
    def test_status_connected(self, mock_get_tok, mock_creds, mock_secret):
        mock_creds.return_value = ("mock_cid", "mock_sec")
        def fake_secret(k):
            if k == "GMAIL_REFRESH_TOKEN":
                return "valid_refresh_token"
            if k == "GMAIL_USER_EMAIL":
                return "test@alj-escalade.fr"
            return None
        mock_secret.side_effect = fake_secret
        mock_get_tok.return_value = "fresh_access_token"

        resp = self.client.get("/api/auth/google/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "connected")
        self.assertTrue(data["valid"])
        self.assertTrue(data["configured"])
        self.assertEqual(data["user_email"], "test@alj-escalade.fr")

    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials")
    def test_login_redirects_to_google(self, mock_creds):
        mock_creds.return_value = ("client_id_test.apps.googleusercontent.com", "secret_test")
        resp = self.client.get("/api/auth/google/login?return_to=/bureau/outils", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        location = resp.headers.get("location", "")
        self.assertTrue(location.startswith("https://accounts.google.com/o/oauth2/auth"))
        self.assertIn("client_id_test", location)
        self.assertIn("access_type=offline", location)
        self.assertIn("prompt=consent", location)
        self.assertIn("state=", location)

    def test_callback_with_error(self):
        resp = self.client.get("/api/auth/google/callback?error=access_denied")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Autorisation Google refusée", resp.text)
        self.assertIn("access_denied", resp.text)

    def test_callback_error_is_escaped(self):
        resp = self.client.get("/api/auth/google/callback", params={"error": XSS})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(XSS, resp.text)
        self.assertNotIn("<img", resp.text)
        self.assertIn("&lt;img", resp.text)

    @patch("requests.post", side_effect=ConnectionError("proxy 10.0.0.12:3128 refused"))
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=("cid", "sec"))
    def test_callback_network_error_is_generic(self, mock_creds, mock_post):
        resp = self.client.get("/api/auth/google/callback?code=mock_code")
        self.assertIn("Échec de la communication avec Google", resp.text)
        self.assertNotIn("10.0.0.12", resp.text)

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.is_enabled", return_value=False)
    @patch("requests.post")
    @patch("requests.get")
    @patch("infrastructure.security.secret_store.SecretStore.set_secret")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=("mock_cid", "mock_sec"))
    def test_callback_rejects_foreign_return_to(self, mock_creds, mock_set_secret, mock_get, mock_post, mock_enabled):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"access_token": "a", "refresh_token": "r"})
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"email": XSS})
        cases = {
            "javascript:alert(1)": '"/bureau/parametres"',
            "//evil.example/x": '"/bureau/parametres"',
            "https://evil.example": '"/bureau/parametres"',
            # a local path stays, as a JSON string: the quote cannot end it
            "/x';alert(1);//</script>": '"/x\';alert(1);//\\u003c/script>"',
        }
        for return_to, js_literal in cases.items():
            with self.subTest(return_to=return_to):
                state = base64.urlsafe_b64encode(json.dumps({"return_to": return_to}).encode()).decode()
                html = self.client.get(f"/api/auth/google/callback?code=c&state={state}").text
                self.assertIn("Connexion Google Réussie", html)
                self.assertIn(f"window.location.href = {js_literal};", html)
                self.assertNotIn("evil.example", html)
                self.assertNotIn("javascript:", html)
                self.assertEqual(html.count("</script>"), 1)
                self.assertNotIn("<img", html)

    def test_safe_return_to(self):
        from api.integrations.google_auth import DEFAULT_RETURN_TO, _safe_return_to
        cases = {
            "/bureau/outils": "/bureau/outils",
            None: DEFAULT_RETURN_TO,
            "": DEFAULT_RETURN_TO,
            "javascript:alert(1)": DEFAULT_RETURN_TO,
            "https://evil.example/": DEFAULT_RETURN_TO,
            "//evil.example/": DEFAULT_RETURN_TO,
            "/\\evil.example/": DEFAULT_RETURN_TO,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(_safe_return_to(value), expected)

    def test_callback_missing_code(self):
        resp = self.client.get("/api/auth/google/callback")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Code d'autorisation manquant", resp.text)

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.sync")
    @patch("requests.post")
    @patch("requests.get")
    @patch("infrastructure.security.secret_store.SecretStore.set_secret")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials")
    def test_callback_success(self, mock_creds, mock_set_secret, mock_get, mock_post, mock_sync):
        mock_creds.return_value = ("mock_cid", "mock_sec")

        post_mock = MagicMock()
        post_mock.status_code = 200
        post_mock.json.return_value = {
            "access_token": "new_access_token_123",
            "refresh_token": "new_refresh_token_456"
        }
        mock_post.return_value = post_mock

        get_mock = MagicMock()
        get_mock.status_code = 200
        get_mock.json.return_value = {"email": "club@alj-escalade.fr"}
        mock_get.return_value = get_mock

        # Préparer un state encodé
        state_data = {"redirect_uri": "http://testserver/api/auth/google/callback", "return_to": "/bureau/outils"}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        resp = self.client.get(f"/api/auth/google/callback?code=mock_code&state={state}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Connexion Google Réussie", resp.text)
        self.assertIn("club@alj-escalade.fr", resp.text)

        # Vérifier que le nouveau refresh token et l'email ont été stockés
        calls = {call[0][0]: call[0][1] for call in mock_set_secret.call_args_list}
        self.assertEqual(calls.get("GMAIL_REFRESH_TOKEN"), "new_refresh_token_456")
        self.assertEqual(calls.get("GMAIL_USER_EMAIL"), "club@alj-escalade.fr")

    @patch("infrastructure.google.drive.GoogleDriveClient.get_access_token")
    @patch("infrastructure.firestore.cloud_database.CloudDatabase.is_enabled")
    @patch("requests.get")
    def test_test_endpoint_success(self, mock_get, mock_db_enabled, mock_get_tok):
        mock_get_tok.return_value = "access_token_ok"
        mock_db_enabled.return_value = False

        gmail_resp = MagicMock()
        gmail_resp.status_code = 200
        gmail_resp.json.return_value = {"emailAddress": "amicale@gmail.com"}
        mock_get.return_value = gmail_resp

        resp = self.client.post("/api/auth/google/test")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["all_ok"])
        self.assertTrue(data["results"]["oauth_token"]["ok"])
        self.assertTrue(data["results"]["database"]["ok"])
        self.assertTrue(data["results"]["gmail"]["ok"])

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.sync")
    @patch("requests.post")
    @patch("requests.get")
    @patch("infrastructure.security.secret_store.SecretStore.set_secret")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials")
    def test_update_token_success(self, mock_creds, mock_set_secret, mock_get, mock_post, mock_sync):
        mock_creds.return_value = ("cid", "sec")
        post_mock = MagicMock()
        post_mock.status_code = 200
        post_mock.json.return_value = {"access_token": "valid_tok"}
        mock_post.return_value = post_mock

        get_mock = MagicMock()
        get_mock.status_code = 200
        get_mock.json.return_value = {"email": "admin@alj-escalade.fr"}
        mock_get.return_value = get_mock

        payload = {"refresh_token": "my_new_refresh_token"}
        resp = self.client.post("/api/auth/google/update-token", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["user_email"], "admin@alj-escalade.fr")

    @patch("glob.glob")
    @patch("builtins.open")
    def test_get_client_credentials_prefer_web(self, mock_open, mock_glob):
        """Vérifie que prefer_web privilégie la configuration 'web' sur 'installed'."""
        from infrastructure.google.drive import GoogleDriveClient
        from infrastructure.security.secret_store import SecretStore
        mock_glob.return_value = ["fake_client_secret.json"]
        fake_data = {
            "web": {"client_id": "mock_web_cid", "client_secret": "mock_web_sec"},
            "installed": {"client_id": "mock_inst_cid", "client_secret": "mock_inst_sec"}
        }
        with patch.object(SecretStore, "get_secret", return_value=""):
            with patch("json.load", return_value=fake_data):
                cid, sec = GoogleDriveClient.get_client_credentials(prefer_web=True)
                self.assertEqual(cid, "mock_web_cid")
                self.assertEqual(sec, "mock_web_sec")


if __name__ == "__main__":
    unittest.main()
