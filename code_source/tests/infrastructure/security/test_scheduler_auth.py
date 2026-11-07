"""Results batch route (audit A29): an admin or the Cloud Scheduler OIDC token, never public."""

from __future__ import annotations

import datetime
import os
import time
import unittest
from unittest.mock import patch

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from infrastructure.security import api_auth
from infrastructure.security.api_auth import Role
from server import app
from services.competitions.results_batch import ResultsBatchError
from support.fake_access import grant_roles

CRON = "/api/competitions/cron/fetch-results"
BATCH = "services.competitions.results_batch.CompetitionResultsBatchService.run_daily_batch"
REPORT = {"status": "success", "executed_at": "2026-10-20T07:00:00", "competitions_checked": 0, "competitions_updated": 0,
          "competitions_remaining": 0, "partial": False, "window_days": 30, "email_sent": False,
          "notification_email": "n@example.org", "details": []}
KID = "scheduler-test-kid"
ADMIN = "minerva@hogwarts.example"
COACH = "severus@hogwarts.example"


def _key_and_cert(common_name: str):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1)
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return key, cert.public_bytes(serialization.Encoding.PEM).decode()


KEY, CERT_PEM = _key_and_cert("google-oidc.test")
OTHER_KEY, _ = _key_and_cert("other.test")


def oidc_token(email: str = api_auth.DEFAULT_SCHEDULER_SERVICE_ACCOUNT, aud: str = api_auth.DEFAULT_SCHEDULER_AUDIENCE,
               key=KEY, iss: str = "https://accounts.google.com", verified: bool = True, exp_delta: int = 3600) -> str:
    now = int(time.time())
    payload = {"iss": iss, "aud": aud, "sub": "1234567890", "iat": now - 10, "exp": now + exp_delta, "email": email,
               "email_verified": verified}
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": KID})


def firebase_claims(email: str) -> dict:
    return {"email": email, "email_verified": True, "sub": "uid"}


class TestSchedulerAuth(unittest.TestCase):

    def setUp(self):
        api_auth._certs_cache.invalidate(api_auth.GOOGLE_OIDC_CERTS_URL)
        api_auth._certs_cache.get_or_load_expiring(api_auth.GOOGLE_OIDC_CERTS_URL, lambda: ({KID: CERT_PEM}, 3600))
        self.addCleanup(api_auth._certs_cache.invalidate, api_auth.GOOGLE_OIDC_CERTS_URL)
        env = patch.dict(os.environ, {"ALJ_API_AUTH": "required"})
        env.start()
        self.addCleanup(env.stop)
        batch = patch(BATCH, return_value=REPORT)
        self.batch = batch.start()
        self.addCleanup(batch.stop)
        self.client = TestClient(app)
        grant_roles({ADMIN: "admin", COACH: "coach"})

    def post(self, token: str = "", query: str = ""):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(CRON + query, headers=headers)

    def test_route_is_no_longer_public(self):
        self.assertNotIn(CRON, api_auth.PUBLIC_PATHS)
        self.assertEqual(api_auth.required_role("POST", CRON), Role.ADMIN)
        r = self.post()
        self.assertEqual(r.status_code, 401)
        self.batch.assert_not_called()

    def test_scheduler_token_runs_the_batch(self):
        r = self.post(oidc_token())
        self.assertEqual(r.status_code, 200, r.text)
        self.batch.assert_called_once_with(force=False, to_email=None)

    def test_scheduler_cannot_force_nor_redirect_the_email(self):
        for query in ("?force=true", "?email=someone@example.org"):
            self.assertEqual(self.post(oidc_token(), query).status_code, 403, query)
        self.batch.assert_not_called()

    def test_other_google_tokens_are_refused(self):
        cases = {
            "another account": (oidc_token(email="someone@gmail.com"), 403),
            "e-mail not verified": (oidc_token(verified=False), 403),
            "another audience": (oidc_token(aud="https://evil.example.org"), 401),
            "expired": (oidc_token(exp_delta=-3600), 401),
            "other signing key": (oidc_token(key=OTHER_KEY), 401),
        }
        for label, (token, status) in cases.items():
            with self.subTest(label):
                self.assertEqual(self.post(token).status_code, status)
        self.batch.assert_not_called()

    def test_audiences_and_account_can_be_configured(self):
        env = {"ALJ_SCHEDULER_AUDIENCES": "https://a.example.org, https://b.example.org/",
               "ALJ_SCHEDULER_SERVICE_ACCOUNT": "job@demo.iam.gserviceaccount.com"}
        with patch.dict(os.environ, env):
            token = oidc_token(email="job@demo.iam.gserviceaccount.com", aud="https://b.example.org")
            self.assertEqual(self.post(token).status_code, 200)

    def test_admin_may_force_and_choose_the_recipient(self):
        with patch.object(api_auth, "verify_firebase_token", return_value=firebase_claims(ADMIN)):
            r = self.post("firebase-token", "?force=true&email=me@example.org")
        self.assertEqual(r.status_code, 200, r.text)
        self.batch.assert_called_once_with(force=True, to_email="me@example.org")

    def test_coach_is_refused(self):
        with patch.object(api_auth, "verify_firebase_token", return_value=firebase_claims(COACH)):
            self.assertEqual(self.post("firebase-token").status_code, 403)
        self.batch.assert_not_called()

    def test_unreadable_competitions_answer_503(self):
        self.batch.side_effect = ResultsBatchError("down")
        r = self.post(oidc_token())
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["status"], "error")
