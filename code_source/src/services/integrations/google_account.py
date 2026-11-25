"""The club's Google account (Gmail API, Drive & Firestore): its connection state, the OAuth2 flow an admin runs to
replace its refresh token, the manual token update and the diagnostic of the Paramètres page.

The OAuth state is signed with the client secret, which only this server knows, so the callback can tell a flow an
admin started here from a forged one (on any Cloud Run instance). Refusals are raised (domain.errors, LoginFailed).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

from domain.errors import InvalidRequest, StorageUnavailable, UpstreamUnavailable
from infrastructure import runtime_env
from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.google import oauth
from infrastructure.google.drive import GoogleDriveClient
from infrastructure.security.secret_store import SecretPersistenceError, SecretStore

logger = logging.getLogger("alj")

DEFAULT_RETURN_TO = "/bureau/parametres"
STATE_MAX_AGE = 600  # seconds between the admin's click and Google's redirect

ConnectionState = Literal["connected", "expired", "disconnected"]
LoginFailure = Literal["not_configured", "bad_state", "unreachable", "refused", "no_refresh_token", "not_saved"]


@dataclass(frozen=True)
class GoogleConnection:
    """db_accessible: the Firestore cache is ready, or the token works; error: shown to the admin (details logged)."""
    state: ConnectionState
    valid: bool
    configured: bool
    client_id_configured: bool
    refresh_token_present: bool
    user_email: str
    db_accessible: bool
    error: str


@dataclass(frozen=True)
class CompletedLogin:
    """user_email: "" when Google did not give it; sync_ok: False when the sync that followed failed (logged)."""
    user_email: str
    return_to: str
    sync_ok: bool


class LoginFailed(Exception):
    """The OAuth return could not be completed. `refused`: Google's status and answer, and the redirect URI to check
    in the Google Cloud console; `return_to`: where the failure page leads back."""

    def __init__(self, reason: LoginFailure, status_code: int = 0, text: str = "", redirect_uri: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code
        self.text = text
        self.redirect_uri = redirect_uri


@dataclass(frozen=True)
class Check:
    ok: bool
    message: str


@dataclass(frozen=True)
class Diagnostic:
    """status: "error" when no access token could be made (the other checks are skipped), else "warning" when a check
    failed, else "success"."""
    status: Literal["success", "warning", "error"]
    oauth_token: Check
    database: Check
    gmail: Check

    @property
    def all_ok(self) -> bool:
        return self.oauth_token.ok and self.database.ok and self.gmail.ok


def safe_return_to(value: Optional[str]) -> str:
    """Page to come back to after the OAuth flow: a path on this site only; anything else (another host,
    javascript:…) is replaced."""
    value = str(value or "").strip()
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return DEFAULT_RETURN_TO


def sign_state(payload: Dict[str, Any], key: str) -> str:  # Any: JSON values
    """OAuth state: base64 JSON + HMAC-SHA256 with the OAuth client secret."""
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    signature = hmac.new(key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def read_state(state: Optional[str], key: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:  # Any: JSON values
    """Payload of a state made by sign_state, or None when it is missing, forged, altered or older than STATE_MAX_AGE."""
    body, _, signature = str(state or "").rpartition(".")
    if not body or not signature:
        return None
    expected = hmac.new(key.encode("utf-8"), body.encode("ascii", "replace"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode("ascii")).decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    age = (time.time() if now is None else now) - float(payload.get("ts") or 0)
    return payload if 0 <= age <= STATE_MAX_AGE else None


def connection() -> GoogleConnection:
    """State of the club's Google connection: an access token is asked of Google (not in dev mode)."""
    if runtime_env.is_dev():
        return GoogleConnection(state="connected", valid=True, configured=True, client_id_configured=True,
                                refresh_token_present=True, user_email="dev-emulator@alj-escalade.fr",
                                db_accessible=CloudDatabase.cache_ready() if CloudDatabase.is_enabled() else True, error="")

    client_id, _ = GoogleDriveClient.get_client_credentials()
    refresh_token = SecretStore.get_secret("GMAIL_REFRESH_TOKEN")
    configured = bool(client_id and refresh_token)
    valid = False
    error = ""
    if configured:
        try:
            valid = bool(GoogleDriveClient.get_access_token())
        except Exception:  # refused, revoked or unreachable: the page asks for a new connection
            logger.exception("[google_connection] Jeton Google refusé")
            error = "Jeton Google refusé ou expiré : reconnectez le compte Google (détails dans les journaux)."
    db_ready = CloudDatabase.cache_ready() if CloudDatabase.is_enabled() else False
    return GoogleConnection(
        state="connected" if valid else ("expired" if refresh_token else "disconnected"),
        valid=valid, configured=configured, client_id_configured=bool(client_id),
        refresh_token_present=bool(refresh_token), user_email=SecretStore.get_secret("GMAIL_USER_EMAIL"),
        db_accessible=db_ready or valid, error=error,
    )


def start_login(redirect_uri: str, return_to: Optional[str], admin_email: str) -> Optional[str]:
    """Google's consent URL for a new refresh token, with a signed state naming the admin; None when no OAuth client
    is configured on the server."""
    client_id, client_secret = GoogleDriveClient.get_client_credentials()
    if not client_id or not client_secret:
        return None
    state = sign_state({"redirect_uri": redirect_uri, "return_to": safe_return_to(return_to), "admin": admin_email,
                        "ts": time.time()}, client_secret)
    return oauth.consent_url(client_id, redirect_uri, state)


def _credentials(client_id: str, client_secret: str, refresh_token: str, user_email: str) -> Dict[str, str]:
    """The Google OAuth secrets to save together; the account's address only when Google gave it."""
    values = {"GMAIL_CLIENT_ID": client_id, "GMAIL_CLIENT_SECRET": client_secret, "GMAIL_REFRESH_TOKEN": refresh_token}
    if user_email:
        values["GMAIL_USER_EMAIL"] = user_email
    return values


def _sync_after_new_credentials() -> bool:
    """Syncs the cache with the credentials just saved; False when it failed (logged, the next sync retries)."""
    if not CloudDatabase.is_enabled():
        return True
    try:
        sync_ok = not CloudDatabase.sync().get("errors")  # sync logs the details of its failures
    except Exception:  # the credentials are saved: a failed sync is reported, never a failed connection
        logger.exception("Synchronisation Firestore après mise à jour des identifiants Google : erreur inattendue")
        sync_ok = False
    if not sync_ok:
        logger.warning("Synchronisation Firestore après mise à jour des identifiants Google échouée")
    return sync_ok


def complete_login(code: str, state: Optional[str], fallback_redirect_uri: str) -> CompletedLogin:
    """Google's return after the consent: exchanges the code for a refresh token and saves the club's credentials.
    Only a flow started by an admin on this server (start_login), less than STATE_MAX_AGE ago. LoginFailed else."""
    client_id, client_secret = GoogleDriveClient.get_client_credentials()
    if not client_id or not client_secret:
        raise LoginFailed("not_configured")
    state_data = read_state(state, client_secret)
    if state_data is None:
        logger.warning("Rappel OAuth Google refusé : paramètre state absent, falsifié ou expiré")
        raise LoginFailed("bad_state")
    redirect_uri = str(state_data.get("redirect_uri") or "") or fallback_redirect_uri
    admin_email = str(state_data.get("admin") or "")

    try:
        tokens = oauth.exchange_code(code, client_id, client_secret, redirect_uri)
    except oauth.GoogleRefused as e:
        raise LoginFailed("refused", e.status_code, e.text, redirect_uri) from e
    except Exception as e:  # any network failure (requests or below), or an unreadable answer: details in the logs
        logger.exception("[google_auth_callback] Google injoignable")
        raise LoginFailed("unreachable") from e
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise LoginFailed("no_refresh_token")
    access_token = tokens.get("access_token")
    user_email = oauth.account_email(access_token) if access_token else ""

    try:
        SecretStore.set_secrets(_credentials(client_id, client_secret, refresh_token, user_email))
    except SecretPersistenceError as e:
        logger.exception("[google_auth_callback save] Identifiants Google non enregistrés")
        raise LoginFailed("not_saved") from e
    logger.info("Identifiants Google du club remplacés par OAuth : compte %s, par l'administrateur %s",
                user_email or "?", admin_email or "? (contrôle des jetons désactivé)")
    return CompletedLogin(user_email=user_email, return_to=safe_return_to(state_data.get("return_to")),
                          sync_ok=_sync_after_new_credentials())


def replace_refresh_token(refresh_token: str, client_id: str = "", client_secret: str = "", user_email: str = "") -> str:
    """Saves a refresh token an admin pasted (and the OAuth client when given), once Google accepted it. Returns the
    account's address: the one given, else Google's, else ""."""
    if not refresh_token:
        raise InvalidRequest("Le refresh token est requis.")
    stored_client_id, stored_client_secret = GoogleDriveClient.get_client_credentials()
    client_id, client_secret = client_id or stored_client_id, client_secret or stored_client_secret
    if not client_id or not client_secret:
        raise InvalidRequest("Client ID ou Client Secret manquant.")
    try:
        access_token = oauth.access_token_of(client_id, client_secret, refresh_token)
    except oauth.GoogleRefused as e:
        raise InvalidRequest(f"Google a rejeté ce jeton : {e.text}") from e
    except Exception as e:  # unreachable, or an unreadable answer
        logger.exception("[update_google_token] Google injoignable")
        raise UpstreamUnavailable("Impossible de joindre Google (détails dans les journaux).") from e

    if not user_email and access_token:
        user_email = oauth.account_email(access_token)
    try:
        SecretStore.set_secrets(_credentials(client_id, client_secret, refresh_token, user_email))
    except SecretPersistenceError as e:
        logger.exception("[update_google_token] Identifiants Google non enregistrés")
        raise StorageUnavailable("Jeton valide, mais non enregistré (détails dans les journaux).") from e
    _sync_after_new_credentials()
    return user_email


def diagnose() -> Diagnostic:
    """Checks live, in order, that an access token can be made, the database syncs, and Gmail answers."""
    try:
        token = GoogleDriveClient.get_access_token()
    except Exception:  # refused, revoked or unreachable: the other checks need the token
        logger.exception("[test_google_auth oauth] Jeton Google refusé")
        return Diagnostic(
            status="error",
            oauth_token=Check(False, "Échec de renouvellement OAuth2 : jeton refusé ou expiré (détails dans les journaux)."),
            database=Check(False, "Test BDD ignoré en raison de l'échec OAuth2."),
            gmail=Check(False, "Test Gmail ignoré en raison de l'échec OAuth2."))
    oauth_token = (Check(True, "Jeton d'accès obtenu avec succès auprès de Google OAuth2.") if token
                   else Check(False, "Le jeton d'accès retourné est vide."))
    checks = Diagnostic(status="success", oauth_token=oauth_token, database=_database_check(), gmail=_gmail_check(token))
    return checks if checks.all_ok else Diagnostic("warning", checks.oauth_token, checks.database, checks.gmail)


def _database_check() -> Check:
    if not CloudDatabase.is_enabled():
        return Check(True, "Base locale opérationnelle (réplication Firestore désactivée).")
    try:
        sync_errors = CloudDatabase.sync().get("errors")  # sync logs the details
    except Exception:  # sync reports its failures; anything else is unexpected
        logger.exception("[test_google_auth database] Synchronisation impossible")
        return Check(False, "Erreur d'accès à la BDD (détails dans les journaux).")
    if sync_errors:
        return Check(False, "Synchronisation Firestore impossible (détails dans les journaux).")
    return Check(True, "Base Firestore synchronisée et opérationnelle.")


def _gmail_check(token: str) -> Check:
    try:
        address = oauth.gmail_address(token)
    except oauth.GoogleRefused as e:
        return Check(False, f"API Gmail HTTP {e.status_code} : {e.text}")
    except Exception:  # unreachable, or an unreadable answer
        logger.exception("[test_google_auth gmail] Gmail injoignable")
        return Check(False, "Erreur lors du test Gmail (détails dans les journaux).")
    return Check(True, f"API Gmail active pour l'adresse : {address or SecretStore.get_secret('GMAIL_USER_EMAIL') or 'ok'}.")
