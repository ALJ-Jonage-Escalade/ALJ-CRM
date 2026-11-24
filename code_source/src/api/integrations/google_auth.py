"""Google OAuth2 renewal of the club credentials (Gmail API, Drive & Firestore).

The callback URL is registered in the Google Cloud console (see README): keep
/api/auth/google/callback as it is.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import time
import urllib.parse
from typing import Any, Dict, Literal, Optional

import requests
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.integrations.schemas import (
    GoogleChecks, GoogleLoginStart, GoogleLoginUrl, GoogleStatus, GoogleTest, GoogleTokenUpdate, GoogleTokenUpdated, ServiceCheck,
)
from api.responses import error, error_responses, internal_error
from infrastructure import runtime_env
from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.google.drive import GoogleDriveClient
from infrastructure.security.secret_store import SecretPersistenceError, SecretStore

logger = logging.getLogger("alj")

router = APIRouter()

DEFAULT_RETURN_TO = "/bureau/parametres"
STATE_MAX_AGE = 600  # seconds between the admin's click and Google's redirect


def _safe_return_to(value: Optional[str]) -> str:
    """Page to come back to after the OAuth flow: a path on this site only; anything else (another host,
    javascript:…) is replaced."""
    value = str(value or "").strip()
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return DEFAULT_RETURN_TO


@router.get("/api/auth/google/status", response_model=GoogleStatus)
def get_google_auth_status() -> GoogleStatus:
    """Vérifie l'état de la connexion Google OAuth2 et la validité du jeton d'accès pour la BDD et Gmail."""
    if runtime_env.is_dev():
        db_ready = CloudDatabase.cache_ready() if CloudDatabase.is_enabled() else True
        return GoogleStatus(
            status="connected",
            valid=True,
            configured=True,
            client_id_configured=True,
            refresh_token_present=True,
            user_email="dev-emulator@alj-escalade.fr",
            db_accessible=db_ready,
            error="",
        )

    client_id, client_secret = GoogleDriveClient.get_client_credentials()
    refresh_token = SecretStore.get_secret("GMAIL_REFRESH_TOKEN")
    user_email = SecretStore.get_secret("GMAIL_USER_EMAIL")

    configured = bool(client_id and refresh_token)
    valid = False
    error_msg = ""
    
    if configured:
        try:
            tok = GoogleDriveClient.get_access_token()
            valid = bool(tok)
        except Exception as e:
            valid = False
            internal_error(e, "get_google_auth_status")
            error_msg = "Jeton Google refusé ou expiré : reconnectez le compte Google (détails dans les journaux)."
            
    db_ready = CloudDatabase.cache_ready() if CloudDatabase.is_enabled() else False

    status: Literal["connected", "expired", "disconnected"] = (
        "connected" if valid else ("expired" if refresh_token else "disconnected"))

    return GoogleStatus(
        status=status,
        valid=valid,
        configured=configured,
        client_id_configured=bool(client_id),
        refresh_token_present=bool(refresh_token),
        user_email=user_email,
        db_accessible=db_ready or valid,
        error=error_msg,
    )


def _callback_url(request: Request) -> str:
    """This server's OAuth callback, as the browser sees it (behind Cloud Run's proxy)."""
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
    # A URL handed to Google and kept in the signed state, not an HTTP response body
    return f"{proto}://{host}/api/auth/google/callback"  # nosemgrep: python.flask.security.audit.directly-returned-format-string.directly-returned-format-string


def _sign_state(payload: Dict[str, Any], key: str) -> str:  # Any: JSON values
    """OAuth state: base64 JSON + HMAC-SHA256 with the OAuth client secret, which only this server knows, so the
    callback can tell a flow an admin started here from a forged one (on any Cloud Run instance)."""
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    signature = hmac.new(key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _read_state(state: Optional[str], key: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:  # Any: JSON values
    """Payload of a state made by _sign_state, or None when it is missing, forged, altered or older than STATE_MAX_AGE."""
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


@router.post("/api/auth/google/login", response_model=GoogleLoginUrl, responses=error_responses(503))
def google_auth_login(request: Request, data: GoogleLoginStart) -> GoogleLoginUrl | JSONResponse:
    """Starts the Google OAuth2 flow that replaces the club's refresh token (admins): answers Google's consent URL,
    with a signed state naming the admin, that the page then opens."""
    client_id, client_secret = GoogleDriveClient.get_client_credentials()
    if not client_id or not client_secret:
        return error(503, "Aucun identifiant client Google (GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET) n'est configuré sur le serveur.")

    redirect_uri = _callback_url(request)
    claims = getattr(request.state, "user", None) or {}  # None: token check off (local server)
    state = _sign_state({
        "redirect_uri": redirect_uri,
        "return_to": _safe_return_to(data.return_to),
        "admin": str(claims.get("email") or ""),
        "ts": time.time(),
    }, client_secret)

    scopes = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/contacts",
        "https://www.googleapis.com/auth/datastore",
    ]
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return GoogleLoginUrl(status="success", url=f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}")


_PAGE_STYLE = """
        body {
            margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #F1F5F9; color: #1E293B; display: flex; align-items: center; justify-content: center; min-height: 90vh;
        }
        .card {
            background: #fff; border-radius: 14px; box-shadow: 0 4px 15px rgba(15,23,42,0.1);
            max-width: 520px; width: 100%; padding: 32px 28px; text-align: center; border: 1px solid #E2E8F0;
        }
        h2 { margin-top: 0; color: #0F172A; font-size: 20px; }
        p { color: #475569; font-size: 14.5px; line-height: 1.5; }
        .badge {
            display: inline-block; padding: 6px 14px; border-radius: 999px; font-weight: 700; font-size: 13px; margin: 12px 0 16px;
        }
        .badge-success { background: #DCFCE7; color: #166534; }
        .badge-error { background: #FEE2E2; color: #991B1B; }
        .btn {
            display: inline-block; padding: 10px 22px; border-radius: 9px; font-size: 14px; font-weight: 700;
            text-decoration: none; color: #fff; background: #2563EB; border: none; cursor: pointer; margin-top: 15px;
        }
        .btn:hover { background: #1D4ED8; }
        .details { text-align: left; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; margin: 15px 0; font-size: 12px; }
"""
SETTINGS_LINK = ("/bureau/parametres", "Retour aux paramètres")
OFFICE_LINK = ("/bureau/outils", "Retour au bureau")


def _render_page(title: str, body_html: str, return_url: str = DEFAULT_RETURN_TO, auto_redirect: bool = False) -> str:
    """The page the browser lands on after Google's redirect. body_html: markup whose variable parts are escaped."""
    # return_url is checked by _safe_return_to; json.dumps + escaped "<" keeps it a JS string
    js_url = json.dumps(_safe_return_to(return_url)).replace("<", "\\u003c")
    redirect_script = f"<script>setTimeout(function() {{ window.location.href = {js_url}; }}, 3500);</script>" if auto_redirect else ""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} — ALJ Escalade</title>
    <style>{_PAGE_STYLE}</style>
    {redirect_script}
</head>
<body>
    <div class="card">
        {body_html}
    </div>
</body>
</html>"""


def _failure_page(title: str, heading: str, badge: str, message_html: str, link: tuple[str, str] = SETTINGS_LINK,
                  status_code: int = 200) -> HTMLResponse:
    """A failed OAuth return: heading, red badge, explanation (markup, escaped by the caller) and a way back."""
    href, label = link
    return HTMLResponse(_render_page(title, f"""<h2>{heading}</h2>
            <div class="badge badge-error">{badge}</div>
            {message_html}
            <p><a href="{href}" class="btn">{label}</a></p>"""), status_code=status_code)


def _exchange_code_for_tokens(code: str, client_id: str, client_secret: str, redirect_uri: str) -> requests.Response:
    """Google's answer to the authorization code (refresh and access tokens when 200). Raises on a network failure."""
    return requests.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=15)


def _google_account_email(access_token: str) -> str:
    """Address of the Google account behind the token, "" when Google does not give it."""
    try:
        response = requests.get("https://www.googleapis.com/oauth2/v3/userinfo",
                                headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        return str(response.json().get("email") or "") if response.status_code == 200 else ""
    except (requests.RequestException, ValueError):  # unreachable, or not JSON: the address is only shown
        logger.warning("Lecture de l'e-mail du compte Google impossible (userinfo)", exc_info=True)
        return ""


@router.get("/api/auth/google/callback", response_class=HTMLResponse)
def google_auth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None)
) -> HTMLResponse:
    """Google's redirect after the consent: exchanges the code for a refresh token and saves the club's credentials."""
    if error:
        return _failure_page("Connexion refusée", "❌ Autorisation Google refusée", f"Erreur : {html.escape(error)}",
                             "<p>La connexion au compte Google a été annulée ou refusée.</p>")
    if not code:
        return _failure_page("Code manquant", "❌ Code d'autorisation manquant", "Requête incomplète",
                             "<p>Google n'a pas transmis de code de validation.</p>")
    client_id, client_secret = GoogleDriveClient.get_client_credentials()
    if not client_id or not client_secret:
        return _failure_page("Configuration incomplète", "❌ Identifiants Google manquants", "GMAIL_CLIENT_ID ou SECRET introuvable",
                             "<p>Impossible d'échanger le code : le client_secret est manquant sur le serveur.</p>")

    # Only a flow started by an admin on this server (POST /api/auth/google/login), less than 10 minutes ago
    state_data = _read_state(state, client_secret)
    if state_data is None:
        logger.warning("Rappel OAuth Google refusé : paramètre state absent, falsifié ou expiré")
        return _failure_page("Lien expiré", "❌ Lien de connexion invalide ou expiré", "Demande non reconnue",
                             "<p>Relancez « Renouveler la connexion Google » depuis la page Paramètres (administrateurs).</p>",
                             status_code=400)
    return_to = _safe_return_to(state_data.get("return_to"))
    redirect_uri = str(state_data.get("redirect_uri") or "") or _callback_url(request)
    admin_email = str(state_data.get("admin") or "")

    try:
        token_response = _exchange_code_for_tokens(code, client_id, client_secret, redirect_uri)
    except Exception as e:  # any network failure (requests or below): the page says so, the details go to the logs
        internal_error(e, "google_auth_callback")
        return _failure_page("Erreur réseau", "❌ Échec de la communication avec Google", "Erreur de connexion",
                             "<p>Le serveur n'a pas pu joindre Google (détails dans les journaux).</p>", OFFICE_LINK)
    if token_response.status_code != 200:
        return _failure_page(
            "Échec d'échange de jeton", "❌ Échange de jeton échoué", f"HTTP {token_response.status_code}",
            f"""<p>Google a refusé l'échange du code d'autorisation :</p>
            <div class="details"><pre style="margin:0; white-space:pre-wrap;">{html.escape(token_response.text)}</pre></div>
            <p><b>Vérification conseillée :</b> assurez-vous que l'URI de redirection suivante est bien autorisée dans votre Google Cloud Console :<br>
            <code>{html.escape(redirect_uri)}</code></p>""", OFFICE_LINK)

    tokens = token_response.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return _failure_page(
            "Refresh Token absent", "⚠️ Google n'a pas renvoyé de Refresh Token", "Consentement incomplet",
            "<p>Pour forcer Google à générer un nouveau refresh token, révoquez l'accès de l'application dans votre "
            "compte Google puis relancez la connexion.</p>", OFFICE_LINK)
    access_token = tokens.get("access_token")
    user_email = _google_account_email(access_token) if access_token else ""

    try:
        SecretStore.set_secrets(_credentials(client_id, client_secret, refresh_token, user_email))
    except SecretPersistenceError as e:
        internal_error(e, "google_auth_callback save")
        return _failure_page(
            "Enregistrement impossible", "❌ Identifiants Google non enregistrés", "Firestore injoignable",
            """<p>Google a validé la connexion, mais le serveur n'a pas pu l'enregistrer : relancez la connexion
            dans quelques minutes (détails dans les journaux).</p>""", status_code=503)
    logger.info("Identifiants Google du club remplacés par OAuth : compte %s, par l'administrateur %s",
                user_email or "?", admin_email or "? (contrôle des jetons désactivé)")

    # Déclencher la synchronisation immédiate de la BDD
    sync_ok = True
    if CloudDatabase.is_enabled():
        try:
            sync_ok = not CloudDatabase.sync().get("errors")  # sync logs its own failures
        except Exception as se:  # the credentials are saved: report a pending sync, never fail the page
            sync_ok = False
            internal_error(se, "google_auth_callback sync")

    # user_email is escaped with html.escape
    email_display = f"Compte connecté : <b>{html.escape(user_email)}</b>" if user_email else "Compte Google connecté"  # nosemgrep: python.django.security.injection.raw-html-format.raw-html-format
    sync_display = ("✅ Base de données synchronisée avec succès." if sync_ok
                    else "⚠️ Connexion rétablie, mais synchro en attente (détails dans les journaux).")
    return HTMLResponse(_render_page(
        "Connexion Réussie",
        f"""<h2>🎉 Connexion Google Réussie !</h2>
        <div class="badge badge-success">Accès BDD & Gmail rétabli</div>
        <p>{email_display}</p>
        <p>{sync_display}</p>
        <p style="font-size:13px; color:#64748B;">Redirection automatique vers le bureau dans quelques secondes…</p>
        <p><a href="{html.escape(return_to)}" class="btn">Retourner au bureau immédiatement</a></p>""",
        return_url=return_to,
        auto_redirect=True
    ))


@router.post("/api/auth/google/test", response_model=GoogleTest)
def test_google_auth() -> GoogleTest:
    """Diagnostique en direct la connexion Google OAuth2, l'accès BDD et l'API Gmail."""
    results = {
        "oauth_token": {"ok": False, "message": ""},
        "database": {"ok": False, "message": ""},
        "gmail": {"ok": False, "message": ""},
    }
    
    # 1. Test Obtention Access Token
    try:
        tok = GoogleDriveClient.get_access_token()
        if tok:
            results["oauth_token"]["ok"] = True
            results["oauth_token"]["message"] = "Jeton d'accès obtenu avec succès auprès de Google OAuth2."
        else:
            results["oauth_token"]["message"] = "Le jeton d'accès retourné est vide."
    except Exception as e:
        internal_error(e, "test_google_auth oauth")
        results["oauth_token"]["message"] = "Échec de renouvellement OAuth2 : jeton refusé ou expiré (détails dans les journaux)."
        results["database"]["message"] = "Test BDD ignoré en raison de l'échec OAuth2."
        results["gmail"]["message"] = "Test Gmail ignoré en raison de l'échec OAuth2."
        return GoogleTest(status="error", all_ok=False, results=_checks(results))

    # 2. Test Accès BDD (Firestore)
    try:
        if CloudDatabase.is_enabled():
            sync_errors = CloudDatabase.sync().get("errors")  # sync logs the details
            results["database"]["ok"] = not sync_errors
            results["database"]["message"] = ("Synchronisation Firestore impossible (détails dans les journaux)." if sync_errors
                                              else "Base Firestore synchronisée et opérationnelle.")
        else:
            results["database"]["ok"] = True
            results["database"]["message"] = "Base locale opérationnelle (réplication Firestore désactivée)."
    except Exception as e:
        results["database"]["ok"] = False
        internal_error(e, "test_google_auth database")
        results["database"]["message"] = "Erreur d'accès à la BDD (détails dans les journaux)."

    # 3. Test API Gmail
    gmail_user = SecretStore.get_secret("GMAIL_USER_EMAIL")
    try:
        url = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
        resp = requests.get(url, headers={"Authorization": f"Bearer {tok}"}, timeout=10)
        if resp.status_code == 200:
            p_data = resp.json()
            email_address = p_data.get("emailAddress", gmail_user or "ok")
            results["gmail"]["ok"] = True
            results["gmail"]["message"] = f"API Gmail active pour l'adresse : {email_address}."
        else:
            results["gmail"]["ok"] = False
            results["gmail"]["message"] = f"API Gmail HTTP {resp.status_code} : {resp.text}"
    except Exception as e:
        results["gmail"]["ok"] = False
        internal_error(e, "test_google_auth gmail")
        results["gmail"]["message"] = "Erreur lors du test Gmail (détails dans les journaux)."

    all_ok = all(r["ok"] for r in results.values())
    return GoogleTest(status="success" if all_ok else "warning", all_ok=all_ok, results=_checks(results))


def _credentials(client_id: str, client_secret: str, refresh_token: str, user_email: str) -> Dict[str, str]:
    """The Google OAuth secrets to save together; the account's address only when Google gave it."""
    values = {"GMAIL_CLIENT_ID": client_id, "GMAIL_CLIENT_SECRET": client_secret, "GMAIL_REFRESH_TOKEN": refresh_token}
    if user_email:
        values["GMAIL_USER_EMAIL"] = user_email
    return values


def _checks(results: Dict[str, Dict[str, Any]]) -> GoogleChecks:  # Any: {"ok": bool, "message": str}
    return GoogleChecks(**{name: ServiceCheck(**check) for name, check in results.items()})


@router.post("/api/auth/google/update-token", response_model=GoogleTokenUpdated, responses=error_responses(400, 502, 503))
def update_google_token(data: GoogleTokenUpdate) -> GoogleTokenUpdated | JSONResponse:
    """Permet à un administrateur de renseigner ou forcer un refresh token manuellement."""
    refresh_token = data.refresh_token
    client_id = data.client_id
    client_secret = data.client_secret
    user_email = data.user_email

    if not refresh_token:
        return error(400, "Le refresh token est requis.")

    cid_exist, sec_exist = GoogleDriveClient.get_client_credentials()
    final_cid = client_id or cid_exist
    final_sec = client_secret or sec_exist

    if not final_cid or not final_sec:
        return error(400, "Client ID ou Client Secret manquant.")

    test_data = {
        "client_id": final_cid,
        "client_secret": final_sec,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data=test_data, timeout=15)
        if r.status_code != 200:
            return error(400, f"Google a rejeté ce jeton : {r.text}")
        access_tok = r.json().get("access_token")
    except Exception as e:
        return error(502, f"Impossible de joindre Google : {internal_error(e, 'update_google_token')}")

    if not user_email and access_tok:
        user_email = _google_account_email(access_tok)

    try:
        SecretStore.set_secrets(_credentials(final_cid, final_sec, refresh_token, user_email))
    except SecretPersistenceError as e:
        return error(503, f"Jeton valide, mais non enregistré : {internal_error(e, 'update_google_token')}")

    if CloudDatabase.is_enabled():
        try:
            sync_failed = bool(CloudDatabase.sync().get("errors"))  # sync logs the details
        except Exception:
            sync_failed = True
            logger.exception("Synchronisation Firestore après mise à jour du jeton Gmail : erreur inattendue")
        if sync_failed:
            logger.warning("Synchronisation Firestore après mise à jour du jeton Gmail échouée")

    return GoogleTokenUpdated(status="success", message="Jeton Google mis à jour et validé avec succès.", user_email=user_email)
