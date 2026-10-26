"""
Authentication of the FastAPI API (Cloud Run).

Principle
---------
- The Vue app (frontend/, installable as a PWA) signs in through Firebase
  Authentication (Google).
  Every API call sends the user's Firebase ID token in the
  ``Authorization: Bearer <ID token>`` header.
- The server checks the token's signature (Google public keys), audience
  (Firebase project), issuer and expiry, then reads the role of the verified
  address in the access list (role_directory: admin / coach / read-only).
  Unreadable list: 503, never 403.
- Every non-public route needs at least the "coach" role; some writes need
  "admin" (fail-closed: a new route is protected by default). Exception: reads
  listed in READONLY_READ_PREFIXES are open to readonly.

Activation
----------
- ``ALJ_API_AUTH=required`` (set in the Dockerfile) or running on Cloud Run
  (``K_SERVICE`` variable injected by the platform): checks on.
- ``ALJ_API_AUTH=off``: checks off (local server of the desktop app, which only
  listens on 127.0.0.1).
"""

from __future__ import annotations

import hmac
import math
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests

from infrastructure import runtime_env
from infrastructure.security import role_directory
from infrastructure.security.role_directory import AccessUnavailable, normalized_email
from infrastructure.security.roles import Role
from infrastructure.security.secret_store import SecretStore
from infrastructure.timed_cache import TimedCache

DEFAULT_PROJECT_ID = "smart-amplifier-510811-n6"
FIREBASE_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)

# Cloud Scheduler (job batch-resultats-competitions) calls the results batch with a Google OIDC token of its own
# service account, whose audience is the service URL: see documentations/guide_deploiement_cloud_run_helloasso.md.
# ALJ_SCHEDULER_SERVICE_ACCOUNT / ALJ_SCHEDULER_AUDIENCES (comma-separated) override the defaults.
SCHEDULER_PATHS = frozenset({"/api/competitions/cron/fetch-results"})
DEFAULT_SCHEDULER_SERVICE_ACCOUNT = "alj-results-scheduler@smart-amplifier-510811-n6.iam.gserviceaccount.com"
DEFAULT_SCHEDULER_AUDIENCE = "https://alj-escalade-api-bdxfydatoa-ew.a.run.app"
GOOGLE_OIDC_CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
GOOGLE_OIDC_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
# Set in the claims of a request authenticated as the scheduler (no user role)
SCHEDULER_CLAIM = "alj_scheduler"

# ---------------------------------------------------------------------------
# Roles: the only judge of access rights (firestore.rules refuses every client). They come from the
# access list (Administration › Accès, Firestore collection access_roles): never an address in the code.
# The web app keeps no copy of them: it reads the role from /api/me.
# ---------------------------------------------------------------------------
ACCESS_UNAVAILABLE_MESSAGE = "Rôle non vérifiable : la liste des accès est momentanément illisible. Réessayez dans un instant."

# Routes accessibles sans authentification (pages statiques, santé, version,
# webhook HelloAsso qui dispose de sa propre vérification).
PUBLIC_PATHS = frozenset({
    "/",
    "/health",
    "/competitions",
    "/competitions/gestion",
    # Sub-pages of the competitions (api/web/pages.py SPA_SUB_PAGES)
    "/competitions/helloasso",
    "/competitions/bilan",
    "/competitions/coachs",
    "/index",
    "/sw.js",
    "/manifest.webmanifest",
    "/runtime-config.js",
    "/favicon.ico",
    "/api/web-version",
    "/webhooks/helloasso",
    "/api/auth/google/login",
    "/api/auth/google/callback",
    "/api/auth/google/status",
})
# Pages et fichiers de l'application web (logo, anciennes adresses) : publics, données protégées.
PUBLIC_PREFIXES = ("/annuaire", "/bureau", "/spa")
# Reads open to the readonly role (competitions view of the mobile app); every other
# route still requires at least "coach".
READONLY_READ_PREFIXES = ("/api/competitions", "/api/coaches", "/api/competition-members")
# Open to any signed-in account, whatever its role: the role is what the route answers. The token
# is verified even when the checks are off (local server): the app shows the role it answers.
SIGNED_IN_PATHS = frozenset({"/api/me"})


class AuthError(Exception):
    """Échec d'authentification (401) ou d'autorisation (403)."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def auth_enforced() -> bool:
    """Le contrôle d'accès est-il actif ? (relu à chaque requête)."""
    mode = (os.environ.get("ALJ_API_AUTH") or "").strip().lower()
    if mode in ("required", "on", "1", "true", "yes"):
        return True
    if mode in ("off", "0", "false", "no", "disabled"):
        return False
    return bool(os.environ.get("K_SERVICE"))


def firebase_project_id() -> str:
    return (
        SecretStore.get_secret("FIREBASE_PROJECT_ID")
        or SecretStore.get_secret("GOOGLE_PROJECT_ID")
        or DEFAULT_PROJECT_ID
    )


def required_role(method: str, path: str) -> Optional[Role]:
    """Rôle minimal exigé pour une requête (None = route publique)."""
    method = (method or "GET").upper()
    if method == "OPTIONS":  # pré-vol CORS
        return None
    if len(path) > 1:
        path = path.rstrip("/")
    if path in PUBLIC_PATHS:
        return None
    if any(path == prefix or path.startswith(prefix + "/") for prefix in PUBLIC_PREFIXES):
        return None
    if method in ("GET", "HEAD") and any(path == ro_prefix or path.startswith(ro_prefix + "/")
                                         for ro_prefix in READONLY_READ_PREFIXES):
        return Role.READONLY
    if path == "/api/planning" and method not in ("GET", "HEAD"):
        return Role.ADMIN  # remplacement du planning complet réservé aux admins ; les coachs modifient les créneaux
    if path == "/api/admin" or path.startswith("/api/admin/"):
        return Role.ADMIN  # Administration (access list, requests, history): reads included
    if path.startswith("/api/attestations"):
        return Role.ADMIN  # attestations réservées aux administrateurs
    if path.startswith("/api/members") and method not in ("GET", "HEAD"):
        return Role.ADMIN  # modification des fiches réservée aux administrateurs
    if path.startswith("/api/email-templates") and method not in ("GET", "HEAD"):
        return Role.ADMIN  # modification des templates d'emails réservée aux administrateurs
    if path.startswith("/api/whatsapp-template") and method not in ("GET", "HEAD"):
        return Role.ADMIN  # modification du template WhatsApp réservée aux administrateurs
    if path.startswith("/api/helloasso/campaigns") and method not in ("GET", "HEAD"):
        return Role.ADMIN  # choix des campagnes HelloAsso actives réservé aux administrateurs ; la liste reste lisible
    if path.startswith("/api/settings") and method not in ("GET", "HEAD"):
        return Role.ADMIN  # modification des paramètres généraux réservée aux administrateurs
    if path == "/api/helloasso/memberships" or path.startswith("/api/helloasso/memberships/"):
        return Role.ADMIN  # import des adhésions HelloAsso (aperçu, import, historique) réservé aux administrateurs
    if path.startswith("/api/ffme") and method not in ("GET", "HEAD"):
        return Role.ADMIN  # imports et modifications FFME réservés aux administrateurs
    if path == "/api/auth/google/update-token" and method not in ("GET", "HEAD"):
        return Role.ADMIN  # mise à jour manuelle des identifiants Google réservée aux administrateurs
    if path in SCHEDULER_PATHS:
        return Role.ADMIN  # results batch: an admin, or the Cloud Scheduler token (authorize_request)
    if path == "/api/cloud-db/sync" and method not in ("GET", "HEAD"):
        return Role.ADMIN  # reconstruction du cache SQLite (coûteuse) réservée aux administrateurs
    return Role.COACH


# ---------------------------------------------------------------------------
# Rôles
# ---------------------------------------------------------------------------
def role_for_claims(claims: Dict[str, Any]) -> Optional[Role]:
    """Role of a signed-in user in the access list (None: no access); AccessUnavailable when the list can't be read."""
    email = verified_email(claims)
    return role_directory.current().role_of(email) if email else None


def verified_email(claims: Dict[str, Any]) -> str:
    """The account's normalised e-mail, only when Google verified it (always the case for a Google sign-in): nobody
    can claim an address they don't own. Empty otherwise."""
    email = normalized_email(claims.get("email"))
    return email if email and claims.get("email_verified") is True else ""


def has_role(claims: Dict[str, Any], needed: Role) -> bool:
    role = role_for_claims(claims)
    return role is not None and role >= needed


# ---------------------------------------------------------------------------
# Vérification du jeton d'identité Firebase
# ---------------------------------------------------------------------------
# One entry per URL of Google keys (Firebase, OIDC of Cloud Scheduler), kept for the max-age of Google's answer
_certs_cache: TimedCache[str, Dict[str, str]] = TimedCache(math.inf)
_last_known_certs: Dict[str, Dict[str, str]] = {}  # per URL, still used when Google can't be reached after they expire


def _fetch_certs(url: str = FIREBASE_CERTS_URL) -> Tuple[Dict[str, str], float]:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    max_age = 3600
    m = re.search(r"max-age=(\d+)", resp.headers.get("Cache-Control", ""))
    if m:
        max_age = int(m.group(1))
    keys = resp.json()
    _last_known_certs[url] = keys
    return keys, max_age


def _public_key_for(kid: str, url: str = FIREBASE_CERTS_URL):
    from cryptography.x509 import load_pem_x509_certificate

    def load() -> Tuple[Dict[str, str], float]:
        return _fetch_certs(url)

    try:
        keys = _certs_cache.get_or_load_expiring(url, load)
        if kid not in keys:  # keys rotated by Google since the last read
            _certs_cache.invalidate(url)
            keys = _certs_cache.get_or_load_expiring(url, load)
    except Exception as e:  # réseau indisponible
        keys = _last_known_certs.get(url, {})
        if kid not in keys:
            raise AuthError(503, f"Clés de vérification Google indisponibles : {e}")
    pem = keys.get(kid)
    if not pem:
        raise AuthError(401, "Jeton signé par une clé inconnue")
    return load_pem_x509_certificate(pem.encode()).public_key()


def verify_firebase_token(token: str) -> Dict[str, Any]:
    """Vérifie un jeton d'identité Firebase et renvoie ses claims (AuthError sinon)."""
    try:
        import jwt  # PyJWT
    except ImportError:
        raise AuthError(503, "Vérification des jetons indisponible (PyJWT non installé)")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise AuthError(401, "Jeton d'authentification illisible")
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise AuthError(401, "Jeton d'authentification invalide (algorithme)")

    project = firebase_project_id()
    try:
        claims = jwt.decode(
            token,
            _public_key_for(header["kid"]),
            algorithms=["RS256"],
            audience=project,
            issuer=f"https://securetoken.google.com/{project}",
            leeway=60,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthError(401, "Session expirée : reconnectez-vous")
    except jwt.PyJWTError as e:
        raise AuthError(401, f"Jeton d'authentification invalide ({e.__class__.__name__})")

    if not str(claims.get("sub") or "").strip():
        raise AuthError(401, "Jeton d'authentification invalide (sujet)")
    auth_time = claims.get("auth_time")
    if auth_time is not None and float(auth_time) > time.time() + 60:
        raise AuthError(401, "Jeton d'authentification invalide (auth_time)")
    return claims


def scheduler_service_account() -> str:
    return (os.environ.get("ALJ_SCHEDULER_SERVICE_ACCOUNT") or DEFAULT_SCHEDULER_SERVICE_ACCOUNT).strip().lower()


def scheduler_audiences() -> list:
    raw = os.environ.get("ALJ_SCHEDULER_AUDIENCES") or DEFAULT_SCHEDULER_AUDIENCE
    return [a.strip().rstrip("/") for a in raw.split(",") if a.strip()]


def _is_google_oidc_token(token: str) -> bool:
    """A Google-signed OIDC token (Cloud Scheduler), as opposed to a Firebase ID token: told apart by its issuer,
    read unverified only to choose the verification (verify_scheduler_token checks everything)."""
    import jwt  # PyJWT

    try:
        # Unverified read of the issuer only, to pick the keys; the token is then fully verified
        unverified = jwt.decode(token, options={"verify_signature": False})  # nosemgrep: python.jwt.security.unverified-jwt-decode.unverified-jwt-decode
    except jwt.PyJWTError:
        return False
    return unverified.get("iss") in GOOGLE_OIDC_ISSUERS


def verify_scheduler_token(token: str) -> Dict[str, Any]:
    """Verifies a Google OIDC token of the Cloud Scheduler service account (signature, audience = service URL,
    issuer, expiry, verified e-mail). Returns its claims with SCHEDULER_CLAIM set; AuthError otherwise."""
    import jwt  # PyJWT

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise AuthError(401, "Jeton d'authentification illisible")
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise AuthError(401, "Jeton d'authentification invalide (algorithme)")
    try:
        claims = jwt.decode(
            token,
            _public_key_for(header["kid"], GOOGLE_OIDC_CERTS_URL),
            algorithms=["RS256"],
            audience=scheduler_audiences(),
            issuer=list(GOOGLE_OIDC_ISSUERS),
            leeway=60,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthError(401, "Jeton Cloud Scheduler expiré")
    except jwt.PyJWTError as e:
        raise AuthError(401, f"Jeton Cloud Scheduler invalide ({e.__class__.__name__})")
    email = str(claims.get("email") or "").strip().lower()
    if claims.get("email_verified") is not True or not constant_time_equals(email, scheduler_service_account()):
        raise AuthError(403, "Accès refusé : ce compte de service n'est pas celui de la tâche planifiée")
    return {**claims, SCHEDULER_CLAIM: True}


def is_scheduler(claims: Optional[Dict[str, Any]]) -> bool:
    return bool(claims and claims.get(SCHEDULER_CLAIM) is True)


def emulator_claims(authorization: Optional[str]) -> Optional[Dict[str, Any]]:
    """Claims of a Firebase Auth emulator token, read without verification (unsigned by design).

    Dev mode only (ALJ_ENV=dev, which requires the emulator and is refused on Cloud Run): token
    checks are off there, and the emulator's tokens cannot be verified anyway. None elsewhere."""

    token = bearer_token(authorization)
    if not token or not runtime_env.is_dev() or auth_enforced():
        return None
    import jwt  # PyJWT

    try:
        # Dev only (checked above): the emulator's tokens are unsigned by design
        return jwt.decode(token, options={"verify_signature": False})  # nosemgrep: python.jwt.security.unverified-jwt-decode.unverified-jwt-decode
    except jwt.PyJWTError:
        return None


def bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def authorize_request(method: str, path: str, authorization: Optional[str]) -> Optional[Dict[str, Any]]:
    """Contrôle d'accès d'une requête. Renvoie les claims (ou None si public /
    contrôle désactivé) ; lève AuthError en cas de refus."""
    if (method or "GET").upper() != "OPTIONS" and path in SIGNED_IN_PATHS:
        token = bearer_token(authorization)
        if not auth_enforced() and (not token or runtime_env.is_dev()):
            return None  # no token: the route answers 401; dev mode: the route reads the emulator's token
        if not token:
            raise AuthError(401, "Authentification requise : connectez-vous avec votre compte Google")
        return verify_firebase_token(token)
    role = required_role(method, path)
    if role is None or not auth_enforced():
        return None
    token = bearer_token(authorization)
    if not token:
        raise AuthError(401, "Authentification requise : connectez-vous avec votre compte Google")
    if path.rstrip("/") in SCHEDULER_PATHS and _is_google_oidc_token(token):
        return verify_scheduler_token(token)
    claims = verify_firebase_token(token)
    try:
        allowed = has_role(claims, role)
    except AccessUnavailable:
        raise AuthError(503, ACCESS_UNAVAILABLE_MESSAGE)
    if not allowed:
        raise AuthError(403, f"Accès refusé : rôle « {role.name.lower()} » requis pour {claims.get('email') or 'ce compte'}")
    return claims


async def auth_middleware(request, call_next):
    """Middleware FastAPI/Starlette appliquant authorize_request à chaque requête."""
    from fastapi.responses import JSONResponse

    try:
        request.state.user = authorize_request(
            request.method, request.url.path, request.headers.get("authorization")
        )
    except AuthError as e:
        headers = {"WWW-Authenticate": "Bearer"} if e.status_code == 401 else None
        return JSONResponse(
            {"status": "error", "message": e.message},
            status_code=e.status_code,
            headers=headers,
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Local server without authentication (desktop app, local runs)
# ---------------------------------------------------------------------------
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "testserver"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _host_name(host: str) -> str:
    host = (host or "").strip().lower()
    if host.startswith("["):  # IPv6 literal: [::1]:8000
        return host.split("]", 1)[0] + "]"
    return host.rsplit(":", 1)[0]


def local_request_error(method: str, host: str, origin: Optional[str],
                        fetch_site: Optional[str], scheme: str = "http") -> Optional[str]:
    """Reason to reject a request to the unauthenticated local server (None = allowed).

    - Host must be a loopback name: blocks DNS rebinding (a foreign domain resolved to 127.0.0.1).
    - Writes must come from the server's own pages: blocks a website the user visits from
      sending requests to the local API (e.g. mass e-mails, member updates).
    """
    if _host_name(host) not in LOCAL_HOSTS:
        return "Host non autorisé"
    if (method or "GET").upper() in SAFE_METHODS:
        return None
    if (fetch_site or "").lower() in ("cross-site", "same-site"):
        return "Requête d'un autre site refusée"
    if origin and origin.rstrip("/").lower() != f"{scheme}://{host}".lower():
        return "Requête d'un autre site refusée"
    return None


async def local_guard_middleware(request, call_next):
    """Protects the local server when the Firebase token check is off (no-op on Cloud Run)."""
    from fastapi.responses import JSONResponse

    if not auth_enforced():
        reason = local_request_error(
            request.method, request.headers.get("host", ""), request.headers.get("origin"),
            request.headers.get("sec-fetch-site"), request.url.scheme)
        if reason:
            return JSONResponse({"status": "error", "message": reason}, status_code=403)
    return await call_next(request)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(str(a).encode(), str(b).encode())
