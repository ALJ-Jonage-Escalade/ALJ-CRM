"""Google OAuth2 renewal of the club credentials (Gmail API, Drive & Firestore).

The callback URL is registered in the Google Cloud console (see README): keep
/api/auth/google/callback as it is.
"""

from __future__ import annotations

import html
import json
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from api.integrations.schemas import GoogleChecks, GoogleStatus, GoogleTest, GoogleTokenUpdate, GoogleTokenUpdated, ServiceCheck
from api.responses import error, error_responses, internal_error
from infrastructure.security.secret_store import SecretStore

router = APIRouter()

DEFAULT_RETURN_TO = "/bureau/parametres"


def _safe_return_to(value: Optional[str]) -> str:
    """Page to come back to after the OAuth flow: a path on this site only. The state that
    carries it is not signed, so anything else (another host, javascript:…) is replaced."""
    value = str(value or "").strip()
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return DEFAULT_RETURN_TO


@router.get("/api/auth/google/status", response_model=GoogleStatus)
def get_google_auth_status() -> GoogleStatus:
    """Vérifie l'état de la connexion Google OAuth2 et la validité du jeton d'accès pour la BDD et Gmail."""
    from infrastructure.google.drive import GoogleDriveClient
    from infrastructure.firestore.cloud_database import CloudDatabase
    
    client_id, client_secret = GoogleDriveClient.get_client_credentials()
    refresh_token = SecretStore.get_secret("GMAIL_REFRESH_TOKEN")
    user_email = SecretStore.get_secret("GMAIL_USER_EMAIL")
    backend = (SecretStore.get_secret("MEMBER_BACKEND") or "firestore").strip().lower()

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

    status = "connected" if valid else ("expired" if refresh_token else "disconnected")

    return GoogleStatus(
        status=status,
        valid=valid,
        configured=configured,
        client_id_configured=bool(client_id),
        refresh_token_present=bool(refresh_token),
        user_email=user_email,
        backend=backend,
        db_accessible=db_ready or valid,
        error=error_msg,
    )


@router.get("/api/auth/google/login")
def google_auth_login(request: Request, return_to: Optional[str] = DEFAULT_RETURN_TO, redirect_uri: Optional[str] = None):
    """Initie le flux d'autorisation OAuth2 Google pour renouveler le refresh token."""
    import base64
    import urllib.parse
    from infrastructure.google.drive import GoogleDriveClient
    
    client_id, _ = GoogleDriveClient.get_client_credentials(prefer_web=True)
    if not client_id:
        return HTMLResponse(
            "<h2>❌ Erreur de configuration Google OAuth2</h2>"
            "<p>Aucun identifiant client Google (GMAIL_CLIENT_ID ou client_secret_*.json) n'a été trouvé sur le serveur.</p>"
            "<p><a href='/bureau/parametres'>Retour aux paramètres</a></p>",
            status_code=500
        )

    # Détecter dynamiquement la redirect_uri
    if not redirect_uri:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        if "," in proto:
            proto = proto.split(",")[0].strip()
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        if "," in host:
            host = host.split(",")[0].strip()
        redirect_uri = f"{proto}://{host}/api/auth/google/callback"

    # Construire le state
    state_payload = {
        "redirect_uri": redirect_uri,
        "return_to": _safe_return_to(return_to),
        "ts": time.time(),
    }
    state = base64.urlsafe_b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")

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
    auth_url = f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"
    return RedirectResponse(auth_url, status_code=302)


@router.get("/api/auth/google/callback", response_class=HTMLResponse)
def google_auth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None)
):
    """Réceptionne le code d'autorisation OAuth2 de Google, échange contre le refresh_token et enregistre les identifiants."""
    import base64
    import requests
    from infrastructure.google.drive import GoogleDriveClient
    from infrastructure.firestore.cloud_database import CloudDatabase

    def _render_page(title: str, body_html: str, return_url: str = DEFAULT_RETURN_TO, auto_redirect: bool = False):
        # return_url is checked by _safe_return_to; json.dumps + escaped "<" keeps it a JS string
        js_url = json.dumps(_safe_return_to(return_url)).replace("<", "\\u003c")
        redirect_script = f"<script>setTimeout(function() {{ window.location.href = {js_url}; }}, 3500);</script>" if auto_redirect else ""
        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} — ALJ Escalade</title>
    <style>
        body {{
            margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #F1F5F9; color: #1E293B; display: flex; align-items: center; justify-content: center; min-height: 90vh;
        }}
        .card {{
            background: #fff; border-radius: 14px; box-shadow: 0 4px 15px rgba(15,23,42,0.1);
            max-width: 520px; width: 100%; padding: 32px 28px; text-align: center; border: 1px solid #E2E8F0;
        }}
        h2 {{ margin-top: 0; color: #0F172A; font-size: 20px; }}
        p {{ color: #475569; font-size: 14.5px; line-height: 1.5; }}
        .badge {{
            display: inline-block; padding: 6px 14px; border-radius: 999px; font-weight: 700; font-size: 13px; margin: 12px 0 16px;
        }}
        .badge-success {{ background: #DCFCE7; color: #166534; }}
        .badge-error {{ background: #FEE2E2; color: #991B1B; }}
        .btn {{
            display: inline-block; padding: 10px 22px; border-radius: 9px; font-size: 14px; font-weight: 700;
            text-decoration: none; color: #fff; background: #2563EB; border: none; cursor: pointer; margin-top: 15px;
        }}
        .btn:hover {{ background: #1D4ED8; }}
        .details {{ text-align: left; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; margin: 15px 0; font-size: 12px; }}
    </style>
    {redirect_script}
</head>
<body>
    <div class="card">
        {body_html}
    </div>
</body>
</html>"""

    if error:
        return _render_page(
            "Connexion refusée",
            f"""<h2>❌ Autorisation Google refusée</h2>
            <div class="badge badge-error">Erreur : {html.escape(error)}</div>
            <p>La connexion au compte Google a été annulée ou refusée.</p>
            <p><a href="/bureau/parametres" class="btn">Retour aux paramètres</a></p>"""
        )

    if not code:
        return _render_page(
            "Code manquant",
            """<h2>❌ Code d'autorisation manquant</h2>
            <div class="badge badge-error">Requête incomplète</div>
            <p>Google n'a pas transmis de code de validation.</p>
            <p><a href="/bureau/parametres" class="btn">Retour aux paramètres</a></p>"""
        )

    # Récupérer return_to et redirect_uri depuis le state
    return_to = DEFAULT_RETURN_TO
    redirect_uri = ""
    if state:
        try:
            raw_state = base64.urlsafe_b64decode(state.encode("utf-8")).decode("utf-8")
            state_data = json.loads(raw_state)
            return_to = _safe_return_to(state_data.get("return_to"))
            redirect_uri = state_data.get("redirect_uri", "")
        except Exception:
            pass

    if not redirect_uri:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        if "," in proto:
            proto = proto.split(",")[0].strip()
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        if "," in host:
            host = host.split(",")[0].strip()
        redirect_uri = f"{proto}://{host}/api/auth/google/callback"

    client_id, client_secret = GoogleDriveClient.get_client_credentials(prefer_web=True)
    if not client_id or not client_secret:
        return _render_page(
            "Configuration incomplète",
            """<h2>❌ Identifiants Google manquants</h2>
            <div class="badge badge-error">GMAIL_CLIENT_ID ou SECRET introuvable</div>
            <p>Impossible d'échanger le code : le client_secret est manquant sur le serveur.</p>
            <p><a href="/bureau/parametres" class="btn">Retour aux paramètres</a></p>"""
        )

    token_url = "https://oauth2.googleapis.com/token"
    token_params = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    
    try:
        token_resp = requests.post(token_url, data=token_params, timeout=15)
    except Exception as e:
        internal_error(e, "google_auth_callback")
        return _render_page(
            "Erreur réseau",
            """<h2>❌ Échec de la communication avec Google</h2>
            <div class="badge badge-error">Erreur de connexion</div>
            <p>Le serveur n'a pas pu joindre Google (détails dans les journaux).</p>
            <p><a href="/bureau/outils" class="btn">Retour au bureau</a></p>"""
        )

    if token_resp.status_code != 200:
        err_detail = html.escape(token_resp.text)
        return _render_page(
            "Échec d'échange de jeton",
            f"""<h2>❌ Échange de jeton échoué</h2>
            <div class="badge badge-error">HTTP {token_resp.status_code}</div>
            <p>Google a refusé l'échange du code d'autorisation :</p>
            <div class="details"><pre style="margin:0; white-space:pre-wrap;">{err_detail}</pre></div>
            <p><b>Vérification conseillée :</b> assurez-vous que l'URI de redirection suivante est bien autorisée dans votre Google Cloud Console :<br>
            <code>{html.escape(redirect_uri)}</code></p>
            <p><a href="/bureau/outils" class="btn">Retour au bureau</a></p>"""
        )

    tokens = token_resp.json()
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")

    if not refresh_token:
        refresh_token = SecretStore.get_secret("GMAIL_REFRESH_TOKEN")

    if not refresh_token:
        return _render_page(
            "Refresh Token absent",
            """<h2>⚠️ Google n'a pas renvoyé de Refresh Token</h2>
            <div class="badge badge-error">Consentement incomplet</div>
            <p>Pour forcer Google à générer un nouveau refresh token, révoquez l'accès de l'application dans votre compte Google puis relancez la connexion.</p>
            <p><a href="/bureau/outils" class="btn">Retour au bureau</a></p>"""
        )

    # Récupérer l'adresse e-mail
    user_email = ""
    if access_token:
        try:
            userinfo_resp = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            if userinfo_resp.status_code == 200:
                user_email = userinfo_resp.json().get("email", "")
        except Exception:
            pass

    # Sauvegarder dans SecretStore
    SecretStore.set_secret("GMAIL_CLIENT_ID", client_id)
    SecretStore.set_secret("GMAIL_CLIENT_SECRET", client_secret)
    SecretStore.set_secret("GMAIL_REFRESH_TOKEN", refresh_token)
    if user_email:
        SecretStore.set_secret("GMAIL_USER_EMAIL", user_email)

    # Déclencher la synchronisation immédiate de la BDD
    sync_ok = True
    if CloudDatabase.is_enabled():
        try:
            CloudDatabase.sync()
        except Exception as se:
            sync_ok = False
            internal_error(se, "google_auth_callback sync")

    email_display = f"Compte connecté : <b>{html.escape(user_email)}</b>" if user_email else "Compte Google connecté"
    sync_display = ("✅ Base de données synchronisée avec succès." if sync_ok
                    else "⚠️ Connexion rétablie, mais synchro en attente (détails dans les journaux).")

    return _render_page(
        "Connexion Réussie",
        f"""<h2>🎉 Connexion Google Réussie !</h2>
        <div class="badge badge-success">Accès BDD & Gmail rétabli</div>
        <p>{email_display}</p>
        <p>{sync_display}</p>
        <details style="margin:16px 0; text-align:left; font-size:12px; background:#F8FAFC; border:1px solid #CBD5E1; border-radius:8px; padding:10px 12px;">
            <summary style="cursor:pointer; font-weight:600; color:#334155;">🔑 Nouveau Refresh Token (pour Cloud Run)</summary>
            <p style="margin:6px 0 4px; color:#64748B; font-size:11.5px;">Le jeton a été synchronisé. Vous pouvez également copier cette valeur dans Cloud Run (GMAIL_REFRESH_TOKEN) :</p>
            <input type="text" readonly value="{html.escape(refresh_token)}" style="width:100%; box-sizing:border-box; padding:6px 8px; font-family:monospace; font-size:11px; background:#FFF; border:1px solid #CBD5E1; border-radius:4px;" onclick="this.select();">
        </details>
        <p style="font-size:13px; color:#64748B;">Redirection automatique vers le bureau dans quelques secondes…</p>
        <p><a href="{html.escape(return_to)}" class="btn">Retourner au bureau immédiatement</a></p>""",
        return_url=return_to,
        auto_redirect=True
    )


@router.post("/api/auth/google/test", response_model=GoogleTest)
def test_google_auth() -> GoogleTest:
    """Diagnostique en direct la connexion Google OAuth2, l'accès BDD et l'API Gmail."""
    import requests
    from infrastructure.google.drive import GoogleDriveClient
    from infrastructure.firestore.cloud_database import CloudDatabase
    
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

    # 2. Test Accès BDD (Firestore ou Drive)
    backend = (SecretStore.get_secret("MEMBER_BACKEND") or "firestore").strip().lower()
    try:
        if backend == "drive":
            db_id = SecretStore.get_secret("GOOGLE_DRIVE_DB_ID")
            if not db_id:
                results["database"]["ok"] = False
                results["database"]["message"] = "GOOGLE_DRIVE_DB_ID non configuré."
            else:
                name = GoogleDriveClient.get_file_name(db_id)
                results["database"]["ok"] = True
                results["database"]["message"] = f"Fichier Drive '{name}' accessible."
        else:
            if CloudDatabase.is_enabled():
                CloudDatabase.ensure_fresh(max_age=10)
                results["database"]["ok"] = True
                results["database"]["message"] = "Base Firestore synchronisée et opérationnelle."
            else:
                results["database"]["ok"] = True
                results["database"]["message"] = "Base locale opérationnelle."
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


def _checks(results: Dict[str, Dict[str, Any]]) -> GoogleChecks:  # Any: {"ok": bool, "message": str}
    return GoogleChecks(**{name: ServiceCheck(**check) for name, check in results.items()})


@router.post("/api/auth/google/update-token", response_model=GoogleTokenUpdated, responses=error_responses(400, 502))
def update_google_token(data: GoogleTokenUpdate) -> GoogleTokenUpdated | JSONResponse:
    """Permet à un administrateur de renseigner ou forcer un refresh token manuellement."""
    import requests
    from infrastructure.google.drive import GoogleDriveClient
    from infrastructure.firestore.cloud_database import CloudDatabase
    
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
        try:
            u_resp = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_tok}"},
                timeout=10
            )
            if u_resp.status_code == 200:
                user_email = u_resp.json().get("email") or ""
        except Exception:
            pass

    SecretStore.set_secret("GMAIL_CLIENT_ID", final_cid)
    SecretStore.set_secret("GMAIL_CLIENT_SECRET", final_sec)
    SecretStore.set_secret("GMAIL_REFRESH_TOKEN", refresh_token)
    if user_email:
        SecretStore.set_secret("GMAIL_USER_EMAIL", user_email)

    if CloudDatabase.is_enabled():
        try:
            CloudDatabase.sync()
        except Exception:
            pass

    return GoogleTokenUpdated(status="success", message="Jeton Google mis à jour et validé avec succès.", user_email=user_email)
