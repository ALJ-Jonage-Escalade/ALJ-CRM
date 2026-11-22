"""
Tests de sécurité de l'API Cloud Run :
- authentification par jeton d'identité Firebase + rôles (seul juge des droits : firestore.rules refuse tout client) ;
- vérification des notifications webhook HelloAsso (jeton secret, relecture API).
"""

import datetime
import os
import re
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

_tests_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_code_root = os.path.dirname(_tests_dir)
_src_dir = os.path.join(_code_root, "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from infrastructure.helloasso import api as helloasso_api
from infrastructure.security import api_auth
from infrastructure.security.api_auth import Role
from services.competitions.helloasso_webhook import HelloAssoWebhookService
from server import app
from support.fake_access import FakeClock, InMemoryAccessStore, grant_roles, install_access, role_entry

PROJECT = api_auth.DEFAULT_PROJECT_ID
KID = "test-kid"

# The access list of these tests (support/fake_access): conftest starts every test with an empty one
ADMIN = "albus@alj-escalade.fr"
COACH = "severus@hogwarts.example"
READONLY = "argus@hogwarts.example"
STRANGER = "pirate@gmail.com"


def list_accounts():
    grant_roles({ADMIN: "admin", COACH: "coach", READONLY: "readonly"})


def _make_key_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "securetoken.test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return key, cert.public_bytes(serialization.Encoding.PEM).decode()


KEY, CERT_PEM = _make_key_and_cert()
OTHER_KEY, _ = _make_key_and_cert()


def make_token(email=ADMIN, key=KEY, kid=KID, aud=PROJECT,
               iss=None, exp_delta=3600, verified=True, **claims):
    now = int(time.time())
    payload = {
        "iss": iss or f"https://securetoken.google.com/{PROJECT}",
        "aud": aud, "sub": "uid-123", "iat": now - 10, "auth_time": now - 10,
        "exp": now + exp_delta, "email": email, "email_verified": verified,
    }
    payload.update(claims)
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


class _CertsMixin:
    def setUp(self):
        list_accounts()
        api_auth._certs_cache.invalidate()
        api_auth._certs_cache.get_or_load_expiring(api_auth.FIREBASE_CERTS_URL, lambda: ({KID: CERT_PEM}, 3600))

    def tearDown(self):
        api_auth._certs_cache.invalidate()


class TestRoles(unittest.TestCase):

    def test_required_role(self):
        r = api_auth.required_role
        for path in ("/", "/health", "/competitions", "/competitions/gestion", "/index", "/sw.js", "/manifest.webmanifest",
                     "/api/web-version", "/webhooks/helloasso", "/annuaire/", "/annuaire/index.html",
                     "/bureau", "/bureau/", "/bureau/adherents", "/spa/assets/index-abc.js", "/annuaire/assets/logo.png"):
            self.assertIsNone(r("GET", path), path)
        self.assertIsNone(r("POST", "/webhooks/helloasso"))
        self.assertIsNone(r("OPTIONS", "/api/send-email"))
        for path in ("/api/send-email", "/api/helloasso/sync", "/api/email-status",
                     "/api/reports/member-stats", "/docs", "/openapi.json", "/api/une-route-future"):
            self.assertEqual(r("GET", path), Role.COACH, path)
        self.assertEqual(r("POST", "/api/planning/item"), Role.COACH)
        self.assertEqual(r("DELETE", "/api/planning/item/3"), Role.COACH)
        self.assertEqual(r("GET", "/api/planning/export"), Role.COACH)
        self.assertEqual(r("GET", "/api/planning"), Role.COACH)
        self.assertEqual(r("GET", "/annuaire-pirate"), Role.COACH)

    def test_readonly_reads(self):
        """Competition views are readable by readonly; their writes and every other route are not."""
        r = api_auth.required_role
        for path in ("/api/competitions", "/api/competitions/123", "/api/coaches",
                     "/api/competition-members"):
            self.assertEqual(r("GET", path), Role.READONLY, path)
            self.assertEqual(r("HEAD", path), Role.READONLY, path)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertEqual(r(method, "/api/competitions/123"), Role.COACH, method)
            self.assertEqual(r(method, "/api/coaches"), Role.COACH, method)
        # /api/members/competitors carries emergency contacts: coach only, like the directory
        for path in ("/api/competitions-pirate", "/api/members", "/api/members/competitors",
                     "/api/helloasso/items", "/api/email-templates"):
            self.assertEqual(r("GET", path), Role.COACH, path)
        for method, path in (("POST", "/api/competitions/archive-past"),
                             ("POST", "/api/competitions/1/participants/2/cancel"),
                             ("POST", "/api/competitions/1/load-group"),
                             ("PUT", "/api/helloasso/items/5/link"),
                             ("PUT", "/api/helloasso/items/5/ignore")):
            self.assertEqual(r(method, path), Role.COACH, path)

    def test_role_for_claims(self):
        """The access list is the only source of roles, for a verified address."""
        list_accounts()
        f = api_auth.role_for_claims
        self.assertEqual(f({"email": ADMIN, "email_verified": True}), Role.ADMIN)
        self.assertEqual(f({"email": " Severus@Hogwarts.EXAMPLE ", "email_verified": True}), Role.COACH)
        self.assertEqual(f({"email": READONLY, "email_verified": True}), Role.READONLY)
        self.assertIsNone(f({"email": "inconnu@gmail.com", "email_verified": True}))
        # Unverified address: no role, even when listed
        self.assertIsNone(f({"email": ADMIN, "email_verified": False}))
        self.assertIsNone(f({"email": ADMIN}))

    def test_former_rules_grant_nothing(self):
        """Neither the club domain nor custom claims give a role any more: only the access list does."""
        list_accounts()
        f = api_auth.role_for_claims
        self.assertIsNone(f({"email": "bureau@alj-escalade.fr", "email_verified": True}))
        self.assertIsNone(f({"email": "a@b.c", "email_verified": True, "coach": True}))
        self.assertIsNone(f({"admin": True}))
        self.assertIsNone(f({"email": "x@hogwarts.example", "email_verified": True, "admin": True, "readonly": True}))

    def test_has_role_follows_the_hierarchy(self):
        list_accounts()
        admin, coach, readonly = ({"email": e, "email_verified": True} for e in (ADMIN, COACH, READONLY))
        self.assertTrue(api_auth.has_role(admin, Role.COACH))
        self.assertTrue(api_auth.has_role(coach, Role.READONLY))
        self.assertFalse(api_auth.has_role(readonly, Role.COACH))
        self.assertFalse(api_auth.has_role({"email": "inconnu@gmail.com", "email_verified": True}, Role.READONLY))
        self.assertLess(Role.READONLY, Role.COACH)
        self.assertLess(Role.COACH, Role.ADMIN)

    def test_admin_routes_require_admin(self):
        r = api_auth.required_role
        for method in ("GET", "POST", "PATCH", "DELETE"):
            for path in ("/api/admin/access/roles", "/api/admin/access/roles/a@b.c", "/api/admin/access/requests",
                         "/api/admin/access/requests/a@b.c/grant", "/api/admin/access/history"):
                self.assertEqual(r(method, path), Role.ADMIN, f"{method} {path}")
        self.assertEqual(r("GET", "/api/administration"), Role.COACH)  # not under /api/admin/
        # Emergency contacts are written through the member routes: admins only
        self.assertEqual(r("POST", "/api/members/update"), Role.ADMIN)
        self.assertEqual(r("POST", "/api/members/create"), Role.ADMIN)

    def test_helloasso_campaign_choice_requires_admin(self):
        """Coaches see the campaigns (Compétitions › HelloAsso), only admins choose the active one."""
        r = api_auth.required_role
        self.assertEqual(r("GET", "/api/helloasso/campaigns"), Role.COACH)
        for kind in ("membership", "competitions"):
            self.assertEqual(r("PUT", f"/api/helloasso/campaigns/{kind}"), Role.ADMIN, kind)

    def test_rules_hold_no_role_list(self):
        """firestore.rules denies every client: roles live in the access list only (plan phase 3)."""
        with open(os.path.join(_code_root, "firestore", "firestore.rules"), encoding="utf-8") as f:
            rules = f.read()
        self.assertNotIn("@", rules)
        self.assertNotIn("request.auth", rules)

    def test_no_personal_address_in_the_code(self):
        """Roles live in the access list, never in code (GDPR): no personal mailbox in the app's sources."""
        personal = re.compile(r"[a-z0-9_.+-]+@(?:gmail|googlemail|orange|wanadoo|free|sfr|laposte|hotmail|outlook|live|yahoo"
                              r"|icloud|me|aol|gmx|protonmail|neuf|bbox)\.[a-z.]+")
        sources = []
        for root in (os.path.join(_code_root, "src"), os.path.join(_code_root, "frontend", "src")):
            sources += [os.path.join(d, n) for d, _, names in os.walk(root) for n in names
                        if n.endswith((".py", ".ts", ".vue", ".js", ".html")) and not n.endswith(".test.ts")]
        self.assertGreater(len(sources), 50)
        found = []
        for path in sources:
            with open(path, encoding="utf-8") as f:
                found += [f"{os.path.relpath(path, _code_root)}: {email}"
                          for email in personal.findall(f.read().lower())]
        self.assertEqual(found, [])


class TestRoleDirectoryFailure(_CertsMixin, unittest.TestCase):
    """The access list can't be read: 503 for everyone but the bootstrap admin, never 403."""

    def setUp(self):
        super().setUp()
        self.clock = FakeClock()
        self.store = InMemoryAccessStore()
        self.store.save_role(role_entry(COACH, "coach"))
        install_access(self.store, self.clock, bootstrap_email="boot@alj-escalade.fr")
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"ALJ_API_AUTH": "required"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def get(self, path, email):
        return self.client.get(path, headers={"Authorization": f"Bearer {make_token(email=email)}"})

    def test_unreadable_list(self):
        self.store.failing = True
        for path in ("/api/me", "/api/email-status"):
            r = self.get(path, COACH)
            self.assertEqual(r.status_code, 503, path)
            self.assertIn("Rôle non vérifiable", r.json()["message"])
        self.assertEqual(self.get("/api/me", "boot@alj-escalade.fr").json()["role"], "admin")
        self.assertEqual(self.get("/api/email-status", "boot@alj-escalade.fr").status_code, 200)

    def test_cached_list_served_within_the_minute(self):
        self.assertEqual(self.get("/api/me", COACH).json()["role"], "coach")
        self.store.failing = True
        self.assertEqual(self.get("/api/me", COACH).json()["role"], "coach")
        self.clock.advance(seconds=61)
        self.assertEqual(self.get("/api/me", COACH).status_code, 503)


class TestTokenVerification(_CertsMixin, unittest.TestCase):

    def test_valid_token(self):
        claims = api_auth.verify_firebase_token(make_token())
        self.assertEqual(claims["email"], ADMIN)

    def assertRejected(self, token, status=401):
        with self.assertRaises(api_auth.AuthError) as ctx:
            api_auth.verify_firebase_token(token)
        self.assertEqual(ctx.exception.status_code, status)

    def test_invalid_tokens(self):
        self.assertRejected("pas-un-jwt")
        self.assertRejected(make_token(exp_delta=-3600))                       # expiré
        self.assertRejected(make_token(aud="autre-projet"))                    # mauvaise audience
        self.assertRejected(make_token(iss="https://accounts.google.com"))     # mauvais émetteur
        self.assertRejected(make_token(key=OTHER_KEY))                         # signature falsifiée
        self.assertRejected(make_token(sub=""))                                # sujet vide
        self.assertRejected(make_token(auth_time=int(time.time()) + 3600))     # auth_time futur
        hs = jwt.encode({"aud": PROJECT, "sub": "x"}, "secret-de-test-suffisamment-long-32o", algorithm="HS256", headers={"kid": KID})
        self.assertRejected(hs)                                                # algorithme HS256

    def test_unknown_kid_refetches(self):
        with patch.object(api_auth, "_fetch_certs", return_value=({KID: CERT_PEM}, 3600)) as fetch:
            self.assertRejected(make_token(kid="inconnu"))
            fetch.assert_called_once()

    def test_unknown_kid_refused_as_unavailable_when_google_is_down(self):
        with patch.object(api_auth, "_fetch_certs", side_effect=OSError("down")), \
                patch.object(api_auth, "_last_known_certs", {api_auth.FIREBASE_CERTS_URL: {KID: CERT_PEM}}):
            with self.assertRaises(api_auth.AuthError) as ctx:
                api_auth.verify_firebase_token(make_token(kid="inconnu"))
        self.assertEqual(ctx.exception.status_code, 503)

    def test_expired_keys_still_used_when_google_is_down(self):
        api_auth._certs_cache.invalidate()
        with patch.object(api_auth, "_fetch_certs", side_effect=OSError("down")), \
                patch.object(api_auth, "_last_known_certs", {api_auth.FIREBASE_CERTS_URL: {KID: CERT_PEM}}):
            self.assertEqual(api_auth.verify_firebase_token(make_token())["sub"], "uid-123")

    def test_keys_kept_for_the_max_age_of_the_answer(self):
        api_auth._certs_cache.invalidate()
        answer = MagicMock(headers={"Cache-Control": "public, max-age=120"})
        answer.json.return_value = {KID: CERT_PEM}
        saved_clock = api_auth._certs_cache.clock
        self.addCleanup(setattr, api_auth._certs_cache, "clock", saved_clock)
        api_auth._certs_cache.clock = lambda: 1000.0
        with patch.object(api_auth.requests, "get", return_value=answer) as get, \
                patch.object(api_auth, "_last_known_certs", {}):
            api_auth._public_key_for(KID)
            api_auth._certs_cache.clock = lambda: 1119.0
            api_auth._public_key_for(KID)
            self.assertEqual(get.call_count, 1)
            api_auth._certs_cache.clock = lambda: 1120.0
            api_auth._public_key_for(KID)
            self.assertEqual(get.call_count, 2)


class TestMeRoute(_CertsMixin, unittest.TestCase):
    """GET /api/me: any signed-in account gets its own role (the pages no longer hold role lists)."""

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)

    def me(self, token=None, **env):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        with patch.dict(os.environ, {"ALJ_API_AUTH": "required", **env}):
            return self.client.get("/api/me", headers=headers)

    def test_requires_a_valid_token(self):
        r = self.me()
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers.get("www-authenticate"), "Bearer")
        self.assertEqual(self.me("abc").status_code, 401)
        self.assertEqual(self.me(make_token(exp_delta=-3600)).status_code, 401)

    def test_role_of_each_account(self):
        cases = [
            (make_token(email=ADMIN), "admin"),
            (make_token(email=COACH), "coach"),
            (make_token(email=READONLY), "readonly"),
            (make_token(email=STRANGER, coach=True), None),                     # custom claims grant nothing
            (make_token(email="bureau@alj-escalade.fr"), None),                 # nor the club domain
            (make_token(email=STRANGER), None),                                 # signed in, no access: 200, not 403
            (make_token(email=ADMIN, verified=False), None),                    # the list needs a verified e-mail
        ]
        for token, role in cases:
            r = self.me(token)
            self.assertEqual(r.status_code, 200, role)
            self.assertEqual(r.json()["role"], role)
        self.assertEqual(self.me(make_token(email=ADMIN)).json()["email"], ADMIN)

    def test_emulator_token_in_dev_mode_only(self):
        """Dev mode (emulator, token checks off): the unsigned emulator token is read as is."""
        emulator_token = jwt.encode({"sub": "dev-snape", "email": COACH, "email_verified": True},
                                    key=None, algorithm="none")
        r = self.me(emulator_token, ALJ_API_AUTH="off", ALJ_ENV="dev")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"email": COACH, "role": "coach", "invitation_expired_at": None})
        # Token checks off outside dev mode (local server): no unverified token is trusted
        self.assertEqual(self.me(emulator_token, ALJ_API_AUTH="off", ALJ_ENV="prod").status_code, 401)
        # Token checks on: the unsigned token is refused, even in dev mode
        self.assertEqual(self.me(emulator_token, ALJ_ENV="dev").status_code, 401)

    def test_local_server_verifies_the_token(self):
        """Token checks off outside dev mode (lancer_site_web.bat): /api/me still verifies the token and answers the role."""
        local = {"ALJ_API_AUTH": "off", "ALJ_ENV": "prod"}
        r = self.me(make_token(email=ADMIN), **local)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"email": ADMIN, "role": "admin", "invitation_expired_at": None})
        self.assertEqual(self.me(make_token(email=COACH), **local).json()["role"], "coach")
        self.assertEqual(self.me(**local).status_code, 401)
        self.assertEqual(self.me("abc", **local).status_code, 401)
        self.assertEqual(self.me(make_token(exp_delta=-3600), **local).status_code, 401)
        self.assertEqual(self.me(make_token(key=OTHER_KEY), **local).status_code, 401)
        # The other routes still need no token there (local server: local_guard_middleware protects them)
        with patch.dict(os.environ, local):
            self.assertIsNone(api_auth.authorize_request("GET", "/api/members", None))
            self.assertIsNone(api_auth.authorize_request("POST", "/api/members/update", "Bearer abc"))


class TestAuthMiddleware(_CertsMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"ALJ_API_AUTH": "required"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        super().tearDown()

    def get(self, path, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(path, headers=headers)

    def test_public_routes(self):
        for path in ("/health", "/api/web-version", "/webhooks/helloasso",
                     "/bureau/", "/bureau/adherents", "/annuaire/assets/logo.png"):
            self.assertEqual(self.get(path).status_code, 200, path)

    def test_protected_routes(self):
        r = self.get("/api/email-status")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers.get("www-authenticate"), "Bearer")
        self.assertEqual(self.get("/api/email-status", "abc").status_code, 401)
        self.assertEqual(self.get("/api/email-status", make_token(email=READONLY)).status_code, 403)
        self.assertEqual(self.get("/api/email-status", make_token(email=STRANGER)).status_code, 403)
        self.assertEqual(self.get("/api/email-status", make_token(email=COACH)).status_code, 200)
        self.assertEqual(self.get("/docs").status_code, 401)
        self.assertEqual(self.client.post("/api/send-email", json={}).status_code, 401)
        self.assertEqual(self.client.post("/api/helloasso/sync").status_code, 401)

    def test_google_credentials_routes(self):
        """Replacing the club's Google credentials is for admins; its status is for staff, never public."""
        coach = {"Authorization": f"Bearer {make_token(email=COACH)}"}
        self.assertEqual(self.client.post("/api/auth/google/login", json={}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/google/login", json={}, headers=coach).status_code, 403)
        self.assertEqual(self.get("/api/auth/google/status").status_code, 401)
        self.assertEqual(self.get("/api/auth/google/status", make_token(email=READONLY)).status_code, 403)
        # Google's redirect comes without the user's token: reachable, but refused without a signed state
        self.assertNotIn(self.get("/api/auth/google/callback?code=c").status_code, (401, 403))

    def test_readonly_role_end_to_end(self):
        """Readonly can read competitions, and nothing else."""
        readonly = make_token(email=READONLY)
        with patch("infrastructure.firestore.competitions.competitions.list_competition_docs", return_value=[]):
            self.assertEqual(self.get("/api/competitions", readonly).status_code, 200)
        self.assertEqual(self.get("/api/email-status", readonly).status_code, 403)
        r = self.client.post("/api/competitions", json={}, headers={"Authorization": f"Bearer {readonly}"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.get("/api/competitions", make_token(email=STRANGER)).status_code, 403)
        self.assertEqual(self.get("/api/competitions").status_code, 401)

    def test_coaches_change_single_planning_slots(self):
        coach = make_token(email=COACH)
        with patch("api.activities.planning.PlanningRepository.delete_planning_item", return_value=True) as delete:
            r = self.client.delete("/api/planning/item/1", headers={"Authorization": f"Bearer {coach}"})
            self.assertEqual(r.status_code, 200)
            delete.assert_called_once_with(1)

    def test_cross_origin_preflight_not_approved(self):
        """No CORS: a foreign site's preflight is never approved, and OPTIONS needs no token."""
        r = self.client.options("/api/send-email", headers={
            "Origin": "https://exemple.fr", "Access-Control-Request-Method": "POST"})
        self.assertNotEqual(r.status_code, 401)
        self.assertNotIn("access-control-allow-origin", r.headers)

    def test_auth_disabled_locally(self):
        with patch.dict(os.environ, {"ALJ_API_AUTH": "off"}):
            self.assertEqual(self.get("/api/email-status").status_code, 200)
        with patch.dict(os.environ, {"ALJ_API_AUTH": "", "K_SERVICE": "alj-escalade-api"}):
            self.assertTrue(api_auth.auth_enforced())
        with patch.dict(os.environ, {"ALJ_API_AUTH": ""}):
            os.environ.pop("K_SERVICE", None)
            self.assertFalse(api_auth.auth_enforced())


VERIFIED_ITEM = {
    "id": 501, "amount": 1500, "state": "Processed",
    "order": {"id": 9001, "formSlug": "competitions"},
    "user": {"firstName": "Lucas", "lastName": "MARTIN"},
    "customFields": [{"name": "Numéro de licence FFME", "answer": "654321"}],
}


class TestWebhookVerification(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def secrets(self, token=""):
        real = api_auth.SecretStore.get_secret
        return patch("services.competitions.helloasso_webhook.SecretStore.get_secret",
                     side_effect=lambda k: token if k == "HELLOASSO_WEBHOOK_TOKEN" else real(k))

    def test_token_required_when_configured(self):
        with self.secrets("s3cret"), patch.object(helloasso_api, "credentials_configured", return_value=False), \
             patch.object(HelloAssoWebhookService, "reconcile_payment_items", return_value={"status": "success"}) as proc:
            r = self.client.post("/webhooks/helloasso", json={"eventType": "Order", "data": {}})
            self.assertEqual(r.status_code, 401)
            r = self.client.post("/webhooks/helloasso?token=faux", json={"eventType": "Order", "data": {}})
            self.assertEqual(r.status_code, 401)
            proc.assert_not_called()
            r = self.client.post("/webhooks/helloasso?token=s3cret", json={"eventType": "Order", "data": {}})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["verified"], "token")
            proc.assert_called_once()

    def test_production_refuses_unverifiable_notifications(self):
        with self.secrets(""), patch.dict(os.environ, {"ALJ_API_AUTH": "required"}), \
             patch.object(helloasso_api, "credentials_configured", return_value=False), \
             patch.object(HelloAssoWebhookService, "reconcile_payment_items") as proc:
            r = self.client.post("/webhooks/helloasso", json={"eventType": "Order", "data": {}})
            self.assertEqual(r.status_code, 503)
            proc.assert_not_called()

    def test_forged_payload_is_replaced_by_api_data(self):
        """Montant/état/licence forgés dans le payload : seules les données API comptent."""
        forged = {"eventType": "Order", "data": {"id": 9001, "items": [
            {"id": 501, "amount": 999999, "state": "Processed",
             "customFields": [{"name": "Licence", "answer": "000000"}]},
            {"id": 777, "amount": 1500, "state": "Processed"},  # inexistant chez HelloAsso
        ]}}
        with self.secrets(""), patch.object(helloasso_api, "credentials_configured", return_value=True), \
             patch.object(helloasso_api, "get_item", side_effect=lambda i: VERIFIED_ITEM if i == 501 else None) as gi, \
             patch.object(HelloAssoWebhookService, "reconcile_payment_items",
                          side_effect=lambda p, items=None: {"status": "success", "items": items}) as proc:
            r = self.client.post("/webhooks/helloasso", json=forged)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["verified"], "api")
            self.assertEqual([c.args[0] for c in gi.call_args_list], [501, 777])
            self.assertEqual(proc.call_args.kwargs["items"], [VERIFIED_ITEM])

    def test_payment_event_resolves_items_through_api(self):
        payload = {"eventType": "Payment", "data": {"id": 42, "amount": 1500, "state": "Authorized"}}
        with patch.object(helloasso_api, "get_payment", return_value={"id": 42, "order": {"id": 9001}, "items": []}), \
             patch.object(helloasso_api, "get_order", return_value={"id": 9001, "items": [{"id": 501}]}), \
             patch.object(helloasso_api, "get_item", return_value=VERIFIED_ITEM):
            self.assertEqual(HelloAssoWebhookService.fetch_verified_items(payload), [VERIFIED_ITEM])

    def test_api_failure_returns_503(self):
        with self.secrets(""), patch.object(helloasso_api, "credentials_configured", return_value=True), \
             patch.object(helloasso_api, "get_item", side_effect=helloasso_api.HelloAssoApiError("timeout")):
            r = self.client.post("/webhooks/helloasso", json={"eventType": "Order", "data": {"items": [{"id": 1}]}})
            self.assertEqual(r.status_code, 503)

    def test_process_webhook_uses_verified_items(self):
        """Avec des articles vérifiés, le contenu du payload n'est pas utilisé."""
        with patch.object(HelloAssoWebhookService, "extract_items_from_payload") as extract, \
             patch("infrastructure.firestore.app_settings.AppSettingsRepository.get", return_value=""), \
             patch("services.competitions.helloasso_webhook.competitions") as competition_store, \
             patch("services.competitions.helloasso_webhook.member_directory") as directory, \
             patch("services.competitions.helloasso_webhook.helloasso_items") as mirror:
            competition_store.list_competitions.return_value = []
            directory.list_members.return_value = []
            mirror.list_helloasso_links.return_value = {}
            mirror.known_helloasso_item_ids.return_value = set()
            report = HelloAssoWebhookService.reconcile_payment_items({"eventType": "Order"}, items=[VERIFIED_ITEM])
            extract.assert_not_called()
            self.assertEqual(report["processed_count"], 1)
            self.assertEqual(report["matched_count"], 0)

    def test_check_token_constant_time(self):
        with self.secrets("abc"):
            self.assertTrue(HelloAssoWebhookService.check_token("abc"))
            self.assertFalse(HelloAssoWebhookService.check_token("abd"))
            self.assertFalse(HelloAssoWebhookService.check_token(None))
        with self.secrets(""):
            self.assertIsNone(HelloAssoWebhookService.check_token("abc"))


if __name__ == "__main__":
    unittest.main()
