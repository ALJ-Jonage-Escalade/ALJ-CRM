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

import requests
from fastapi.testclient import TestClient
from server import app
from infrastructure.google.drive import GoogleAuthError
from infrastructure.security.secret_store import SecretPersistenceError

XSS = '"><img src=x onerror=alert(1)>'
CLIENT_SECRET = "mock_sec"


def signed_state(**payload):
    """State as POST /api/auth/google/login makes it, signed with the mocked client secret."""
    import time
    from services.integrations.google_account import sign_state as _sign_state
    return _sign_state({"ts": time.time(), **payload}, CLIENT_SECRET)


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
        mock_get_tok.side_effect = GoogleAuthError("400 - invalid_grant")

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
    def test_login_answers_google_url_with_signed_state(self, mock_creds):
        import urllib.parse
        from services.integrations.google_account import read_state as _read_state
        mock_creds.return_value = ("client_id_test.apps.googleusercontent.com", CLIENT_SECRET)
        resp = self.client.post("/api/auth/google/login", json={"return_to": "/bureau/outils"})
        self.assertEqual(resp.status_code, 200)
        location = resp.json()["url"]
        self.assertTrue(location.startswith("https://accounts.google.com/o/oauth2/auth"))
        self.assertIn("client_id_test", location)
        self.assertIn("access_type=offline", location)
        self.assertIn("prompt=consent", location)
        state = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["state"][0]
        self.assertEqual(_read_state(state, CLIENT_SECRET)["return_to"], "/bureau/outils")
        self.assertIsNone(_read_state(state, "another secret"))

    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=(None, None))
    def test_login_without_client_credentials(self, mock_creds):
        self.assertEqual(self.client.post("/api/auth/google/login", json={}).status_code, 503)

    def test_state_signature_and_expiry(self):
        from services.integrations.google_account import STATE_MAX_AGE, read_state as _read_state, sign_state as _sign_state
        state = _sign_state({"ts": 1000.0, "return_to": "/bureau"}, CLIENT_SECRET)
        self.assertEqual(_read_state(state, CLIENT_SECRET, now=1000.0 + STATE_MAX_AGE)["return_to"], "/bureau")
        self.assertIsNone(_read_state(state, CLIENT_SECRET, now=1001.0 + STATE_MAX_AGE))  # expired
        body, _, signature = state.rpartition(".")
        forged = base64.urlsafe_b64encode(json.dumps({"ts": 1000.0, "return_to": "/x"}).encode()).decode()
        for value in (None, "", body, f"{forged}.{signature}", f"{body}.{'0' * 64}", "not.base64!"):
            with self.subTest(state=value):
                self.assertIsNone(_read_state(value, CLIENT_SECRET, now=1000.0))

    @patch("requests.post")
    @patch("infrastructure.security.secret_store.SecretStore.set_secrets")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=("mock_cid", CLIENT_SECRET))
    def test_callback_refuses_unsigned_state(self, mock_creds, mock_set_secret, mock_post):
        """A flow not started by an admin here (old unsigned state, forged one): no code exchange, nothing stored."""
        unsigned = base64.urlsafe_b64encode(json.dumps({"return_to": "/bureau"}).encode()).decode()
        for state in (None, unsigned, signed_state(return_to="/bureau") + "0"):
            with self.subTest(state=state):
                params = {"code": "c"} | ({"state": state} if state else {})
                resp = self.client.get("/api/auth/google/callback", params=params)
                self.assertEqual(resp.status_code, 400)
                self.assertIn("invalide ou expiré", resp.text)
        mock_post.assert_not_called()
        mock_set_secret.assert_not_called()

    @patch("requests.post")
    @patch("infrastructure.security.secret_store.SecretStore.get_secret", return_value="stored_refresh_token")
    @patch("infrastructure.security.secret_store.SecretStore.set_secrets")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=("mock_cid", CLIENT_SECRET))
    def test_callback_without_refresh_token_never_shows_the_stored_one(self, mock_creds, mock_set_secret, mock_get_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"access_token": "a"})
        resp = self.client.get("/api/auth/google/callback", params={"code": "c", "state": signed_state()})
        self.assertIn("pas renvoyé de Refresh Token", resp.text)
        self.assertNotIn("stored_refresh_token", resp.text)
        mock_set_secret.assert_not_called()

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
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=("cid", CLIENT_SECRET))
    def test_callback_network_error_is_generic(self, mock_creds, mock_post):
        resp = self.client.get("/api/auth/google/callback", params={"code": "mock_code", "state": signed_state()})
        self.assertIn("Échec de la communication avec Google", resp.text)
        self.assertNotIn("10.0.0.12", resp.text)

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.is_enabled", return_value=False)
    @patch("requests.post")
    @patch("requests.get")
    @patch("infrastructure.security.secret_store.SecretStore.set_secrets")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=("mock_cid", CLIENT_SECRET))
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
                html = self.client.get("/api/auth/google/callback", params={"code": "c", "state": signed_state(return_to=return_to)}).text
                self.assertIn("Connexion Google Réussie", html)
                self.assertIn(f"window.location.href = {js_literal};", html)
                self.assertNotIn("evil.example", html)
                self.assertNotIn("javascript:", html)
                self.assertEqual(html.count("</script>"), 1)
                self.assertNotIn("<img", html)

    def test_safe_return_to(self):
        from services.integrations.google_account import DEFAULT_RETURN_TO, safe_return_to as _safe_return_to
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

    @patch("requests.post")
    @patch("infrastructure.security.secret_store.SecretStore.set_secrets",
                  side_effect=SecretPersistenceError("Firestore down"))
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=("mock_cid", CLIENT_SECRET))
    def test_callback_reports_credentials_it_could_not_save(self, mock_creds, mock_set_secrets, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"access_token": "a", "refresh_token": "r"})
        with patch("requests.get", return_value=MagicMock(status_code=500)):
            resp = self.client.get("/api/auth/google/callback", params={"code": "c", "state": signed_state()})
        self.assertEqual(resp.status_code, 503)
        self.assertIn("non enregistrés", resp.text)
        self.assertNotIn("Réussie", resp.text)

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.sync", return_value={})
    @patch("requests.post")
    @patch("requests.get")
    @patch("infrastructure.security.secret_store.SecretStore.set_secrets")
    @patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials")
    def test_callback_success(self, mock_creds, mock_set_secret, mock_get, mock_post, mock_sync):
        mock_creds.return_value = ("mock_cid", CLIENT_SECRET)

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

        state = signed_state(redirect_uri="http://testserver/api/auth/google/callback", return_to="/bureau/outils",
                             admin="albus.dumbledore@alj-escalade.fr")

        with self.assertLogs("alj", "INFO") as logs:
            resp = self.client.get("/api/auth/google/callback", params={"code": "mock_code", "state": state})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Connexion Google Réussie", resp.text)
        self.assertIn("club@alj-escalade.fr", resp.text)
        self.assertNotIn("new_refresh_token_456", resp.text)  # the token never reaches a page
        self.assertTrue(any("albus.dumbledore@alj-escalade.fr" in line for line in logs.output))
        self.assertEqual(mock_post.call_args.kwargs["data"]["redirect_uri"], "http://testserver/api/auth/google/callback")

        # Vérifier que le nouveau refresh token et l'email ont été stockés
        mock_set_secret.assert_called_once()  # one write: never a mix of old and new credentials
        calls = mock_set_secret.call_args.args[0]
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

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.sync", return_value={})
    @patch("requests.post")
    @patch("requests.get")
    @patch("infrastructure.security.secret_store.SecretStore.set_secrets")
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


def http_response(status_code, payload=None, text=""):
    response = MagicMock(status_code=status_code, text=text)
    response.json.return_value = payload or {}
    return response


def replication_on(test):
    """Firestore replication as on Cloud Run (tests/conftest.py turns it off)."""
    patcher = patch.dict(os.environ, {"ALJ_CACHE_REPLICATION": "on"})
    patcher.start()
    test.addCleanup(patcher.stop)


@patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=("mock_cid", CLIENT_SECRET))
class TestGoogleAuthCallbackFailures(unittest.TestCase):
    """The consent callback when Google refuses the code, or after saving the credentials, the sync fails."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def callback(self):
        state = signed_state(redirect_uri="http://testserver/api/auth/google/callback", return_to="/bureau")
        return self.client.get("/api/auth/google/callback", params={"code": "mock_code", "state": state})

    @patch("requests.post", return_value=http_response(400, text='{"error": "invalid_grant <b>"}'))
    def test_refused_code_shows_google_answer_escaped(self, _post, _creds):
        resp = self.callback()
        self.assertIn("HTTP 400", resp.text)
        self.assertIn("invalid_grant &lt;b&gt;", resp.text)
        self.assertNotIn("Réussie", resp.text)

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.sync", return_value={"errors": ["Firestore down"]})
    @patch("infrastructure.security.secret_store.SecretStore.set_secrets")
    @patch("requests.get", side_effect=requests.ConnectionError("userinfo down"))
    @patch("requests.post", return_value=http_response(200, {"access_token": "tok", "refresh_token": "refresh"}))
    def test_saved_credentials_with_failed_sync_and_no_address_still_succeed(self, _post, _get, mock_set, _sync, _creds):
        replication_on(self)
        resp = self.callback()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Compte Google connecté", resp.text)
        self.assertIn("synchro en attente", resp.text)
        self.assertNotIn("GMAIL_USER_EMAIL", mock_set.call_args.args[0])


@patch("requests.get", return_value=http_response(200, {"emailAddress": "club@example.org"}))
@patch("infrastructure.google.drive.GoogleDriveClient.get_access_token", return_value="tok")
class TestGoogleAuthDiagnostic(unittest.TestCase):
    """POST /api/auth/google/test: each check reports its own failure without hiding the others."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def results(self):
        return self.client.post("/api/auth/google/test").json()

    def test_refused_token_skips_the_other_checks(self, mock_token, mock_get):
        mock_token.side_effect = GoogleAuthError("invalid_grant")
        data = self.results()
        self.assertEqual((data["status"], data["all_ok"]), ("error", False))
        self.assertIn("ignoré", data["results"]["gmail"]["message"])
        mock_get.assert_not_called()

    def test_empty_token_is_not_ok(self, mock_token, _get):
        mock_token.return_value = ""
        data = self.results()
        self.assertEqual(data["status"], "warning")
        self.assertFalse(data["results"]["oauth_token"]["ok"])

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.sync", return_value={"errors": ["down"]})
    def test_database_failure_is_reported(self, _sync, _token, _get):
        replication_on(self)
        data = self.results()
        self.assertEqual(data["status"], "warning")
        self.assertFalse(data["results"]["database"]["ok"])
        self.assertTrue(data["results"]["gmail"]["ok"])

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.sync", return_value={"pulled": 0})
    def test_synced_database_is_ok(self, mock_sync, _token, _get):
        replication_on(self)
        self.assertTrue(self.results()["all_ok"])
        mock_sync.assert_called_once_with()

    def test_gmail_http_and_network_failures(self, _token, mock_get):
        for answer in ({"return_value": http_response(403, text="insufficientPermissions")},
                       {"side_effect": requests.ConnectionError("down")}):
            with self.subTest(answer=answer):
                mock_get.configure_mock(**answer)
                gmail = self.results()["results"]["gmail"]
                self.assertFalse(gmail["ok"])
                mock_get.reset_mock(return_value=True, side_effect=True)


@patch("infrastructure.google.drive.GoogleDriveClient.get_client_credentials", return_value=("cid", "sec"))
class TestGoogleTokenUpdateFailures(unittest.TestCase):
    """POST /api/auth/google/update-token: refused requests and failures, nothing saved before Google accepts."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def update(self, **payload):
        return self.client.post("/api/auth/google/update-token", json={"refresh_token": "refresh", **payload})

    @patch("infrastructure.security.secret_store.SecretStore.set_secrets")
    def test_requests_refused_before_calling_google(self, mock_set, mock_creds):
        self.assertEqual(self.update(refresh_token="").status_code, 400)
        mock_creds.return_value = (None, None)
        self.assertEqual(self.update().status_code, 400)
        mock_set.assert_not_called()

    @patch("infrastructure.security.secret_store.SecretStore.set_secrets")
    def test_google_failures(self, mock_set, _creds):
        with patch("requests.post", return_value=http_response(400, text="invalid_grant")):
            self.assertEqual(self.update().status_code, 400)
        with patch("requests.post", side_effect=requests.ConnectionError("down")):
            self.assertEqual(self.update().status_code, 502)
        mock_set.assert_not_called()

    @patch("requests.post", return_value=http_response(200, {"access_token": "tok"}))
    @patch("infrastructure.security.secret_store.SecretStore.set_secrets", side_effect=SecretPersistenceError("down"))
    def test_unsaved_token_is_a_503(self, _set, _post, _creds):
        self.assertEqual(self.update(user_email="club@example.org").status_code, 503)

    @patch("infrastructure.firestore.cloud_database.CloudDatabase.sync", return_value={"errors": ["down"]})
    @patch("requests.post", return_value=http_response(200, {"access_token": "tok"}))
    @patch("infrastructure.security.secret_store.SecretStore.set_secrets")
    def test_saved_token_with_failed_sync_is_a_success(self, mock_set, _post, mock_sync, _creds):
        replication_on(self)
        with self.assertLogs("alj", "WARNING"):
            resp = self.update(client_id="new-cid", client_secret="new-sec", user_email="club@example.org")  # noqa: S106 - fake credential of the test
        self.assertEqual(resp.status_code, 200)
        mock_sync.assert_called_once()
        self.assertEqual(mock_set.call_args.args[0]["GMAIL_CLIENT_ID"], "new-cid")


if __name__ == "__main__":
    unittest.main()
