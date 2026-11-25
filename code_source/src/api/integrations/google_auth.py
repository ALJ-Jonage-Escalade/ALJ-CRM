"""Google OAuth2 renewal of the club credentials (Gmail API, Drive & Firestore): the routes and the pages the browser
lands on after Google's redirect. The flows are in services/integrations/google_account.py.

The callback URL is registered in the Google Cloud console (see README): keep
/api/auth/google/callback as it is.
"""

from __future__ import annotations

import html
import json
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.integrations.schemas import (
    GoogleChecks, GoogleLoginStart, GoogleLoginUrl, GoogleStatus, GoogleTest, GoogleTokenUpdate, GoogleTokenUpdated, ServiceCheck,
)
from api.responses import error, error_responses
from services.integrations import google_account
from services.integrations.google_account import DEFAULT_RETURN_TO, LoginFailed, safe_return_to

router = APIRouter()


@router.get("/api/auth/google/status", response_model=GoogleStatus)
def get_google_auth_status() -> GoogleStatus:
    """Vérifie l'état de la connexion Google OAuth2 et la validité du jeton d'accès pour la BDD et Gmail."""
    connection = google_account.connection()
    return GoogleStatus(
        status=connection.state,
        valid=connection.valid,
        configured=connection.configured,
        client_id_configured=connection.client_id_configured,
        refresh_token_present=connection.refresh_token_present,
        user_email=connection.user_email,
        db_accessible=connection.db_accessible,
        error=connection.error,
    )


def _callback_url(request: Request) -> str:
    """This server's OAuth callback, as the browser sees it (behind Cloud Run's proxy)."""
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
    # A URL handed to Google and kept in the signed state, not an HTTP response body
    return f"{proto}://{host}/api/auth/google/callback"  # nosemgrep: python.flask.security.audit.directly-returned-format-string.directly-returned-format-string


@router.post("/api/auth/google/login", response_model=GoogleLoginUrl, responses=error_responses(503))
def google_auth_login(request: Request, data: GoogleLoginStart) -> GoogleLoginUrl | JSONResponse:
    """Starts the Google OAuth2 flow that replaces the club's refresh token (admins): answers Google's consent URL,
    with a signed state naming the admin, that the page then opens."""
    claims = getattr(request.state, "user", None) or {}  # None: token check off (local server)
    url = google_account.start_login(_callback_url(request), data.return_to, str(claims.get("email") or ""))
    if url is None:
        return error(503, "Aucun identifiant client Google (GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET) n'est configuré sur le serveur.")
    return GoogleLoginUrl(status="success", url=url)


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
    # return_url is checked by safe_return_to; json.dumps + escaped "<" keeps it a JS string
    js_url = json.dumps(safe_return_to(return_url)).replace("<", "\\u003c")
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


def _login_failure_page(failure: LoginFailed) -> HTMLResponse:
    """The page explaining why the OAuth return could not be completed."""
    if failure.reason == "not_configured":
        return _failure_page("Configuration incomplète", "❌ Identifiants Google manquants", "GMAIL_CLIENT_ID ou SECRET introuvable",
                             "<p>Impossible d'échanger le code : le client_secret est manquant sur le serveur.</p>")
    if failure.reason == "bad_state":
        return _failure_page("Lien expiré", "❌ Lien de connexion invalide ou expiré", "Demande non reconnue",
                             "<p>Relancez « Renouveler la connexion Google » depuis la page Paramètres (administrateurs).</p>",
                             status_code=400)
    if failure.reason == "unreachable":
        return _failure_page("Erreur réseau", "❌ Échec de la communication avec Google", "Erreur de connexion",
                             "<p>Le serveur n'a pas pu joindre Google (détails dans les journaux).</p>", OFFICE_LINK)
    if failure.reason == "refused":
        return _failure_page(
            "Échec d'échange de jeton", "❌ Échange de jeton échoué", f"HTTP {failure.status_code}",
            f"""<p>Google a refusé l'échange du code d'autorisation :</p>
            <div class="details"><pre style="margin:0; white-space:pre-wrap;">{html.escape(failure.text)}</pre></div>
            <p><b>Vérification conseillée :</b> assurez-vous que l'URI de redirection suivante est bien autorisée dans votre Google Cloud Console :<br>
            <code>{html.escape(failure.redirect_uri)}</code></p>""", OFFICE_LINK)
    if failure.reason == "no_refresh_token":
        return _failure_page(
            "Refresh Token absent", "⚠️ Google n'a pas renvoyé de Refresh Token", "Consentement incomplet",
            "<p>Pour forcer Google à générer un nouveau refresh token, révoquez l'accès de l'application dans votre "
            "compte Google puis relancez la connexion.</p>", OFFICE_LINK)
    return _failure_page(
        "Enregistrement impossible", "❌ Identifiants Google non enregistrés", "Firestore injoignable",
        """<p>Google a validé la connexion, mais le serveur n'a pas pu l'enregistrer : relancez la connexion
        dans quelques minutes (détails dans les journaux).</p>""", status_code=503)


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
    try:
        login = google_account.complete_login(code, state, _callback_url(request))
    except LoginFailed as failure:
        return _login_failure_page(failure)

    # user_email is escaped with html.escape
    email_display = f"Compte connecté : <b>{html.escape(login.user_email)}</b>" if login.user_email else "Compte Google connecté"  # nosemgrep: python.django.security.injection.raw-html-format.raw-html-format
    sync_display = ("✅ Base de données synchronisée avec succès." if login.sync_ok
                    else "⚠️ Connexion rétablie, mais synchro en attente (détails dans les journaux).")
    return HTMLResponse(_render_page(
        "Connexion Réussie",
        f"""<h2>🎉 Connexion Google Réussie !</h2>
        <div class="badge badge-success">Accès BDD & Gmail rétabli</div>
        <p>{email_display}</p>
        <p>{sync_display}</p>
        <p style="font-size:13px; color:#64748B;">Redirection automatique vers le bureau dans quelques secondes…</p>
        <p><a href="{html.escape(login.return_to)}" class="btn">Retourner au bureau immédiatement</a></p>""",
        return_url=login.return_to,
        auto_redirect=True
    ))


@router.post("/api/auth/google/test", response_model=GoogleTest)
def test_google_auth() -> GoogleTest:
    """Diagnostique en direct la connexion Google OAuth2, l'accès BDD et l'API Gmail."""
    diagnostic = google_account.diagnose()
    checks = GoogleChecks(**{name: ServiceCheck(ok=check.ok, message=check.message) for name, check in (
        ("oauth_token", diagnostic.oauth_token), ("database", diagnostic.database), ("gmail", diagnostic.gmail))})
    return GoogleTest(status=diagnostic.status, all_ok=diagnostic.all_ok, results=checks)


@router.post("/api/auth/google/update-token", response_model=GoogleTokenUpdated, responses=error_responses(400, 502, 503))
def update_google_token(data: GoogleTokenUpdate) -> GoogleTokenUpdated:
    """Permet à un administrateur de renseigner ou forcer un refresh token manuellement."""
    user_email = google_account.replace_refresh_token(data.refresh_token, data.client_id, data.client_secret, data.user_email)
    return GoogleTokenUpdated(status="success", message="Jeton Google mis à jour et validé avec succès.", user_email=user_email)
