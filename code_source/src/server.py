import os
import sys
import json
import time
import datetime
from typing import List, Dict, Any

# S'assurer que le dossier src est dans sys.path (exécution directe, docker ou package)
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from typing import Optional

from fastapi import FastAPI, Body, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response

from dotenv import load_dotenv
load_dotenv()

from infrastructure.security.secret_store import SecretStore
from infrastructure import runtime_env

# Inconsistent dev mode (Firebase emulator) or dev mode on Cloud Run: stop immediately.
runtime_env.validate()


app = FastAPI(title="Admin Escalade API")

# Access control (Firebase token + firestore.rules roles): enforced on Cloud Run and in the
# Docker image (ALJ_API_AUTH=required), off for the desktop app's local server, which is
# protected by local_guard_middleware instead (loopback hosts, same-origin writes).
import re
from fastapi.routing import APIRoute
from infrastructure.firestore.cloud_database import CloudDatabase
from starlette.concurrency import run_in_threadpool


# Paths of the routes that only read/write Firestore collections (competitions, coaches,
# projections, HelloAsso mirror) through CompetitionFirestoreRepository: they never touch the
# SQLite cache, so they must not wait for its refresh (a full rebuild after a cold start).
# Filled from their routers once included (below). Exact routes, not path prefixes: other routes
# under /api/competitions (results batch, check-all-paid) use the cache.
FIRESTORE_ONLY_PATHS: List[re.Pattern[str]] = []


def uses_sqlite_cache(path: str) -> bool:
    """True for the data routes served from the SQLite cache of the crm_* collections."""
    if any(p.match(path) for p in FIRESTORE_ONLY_PATHS):
        return False
    return path.startswith("/api/") or path in ("/map", "/pivot")


async def cloud_db_middleware(request, call_next):
    """Base principale dans Firestore : le cache SQLite du serveur est mis à jour
    avant les routes de données, et les écritures sont envoyées juste après.
    Enregistré avant le contrôle d'accès : il ne s'exécute qu'après lui."""
    relevant = uses_sqlite_cache(request.url.path)
    # Cloud Run, or local dev on the emulator: the cache follows Firestore as in production
    server_mode = os.environ.get("K_SERVICE") or runtime_env.is_dev()
    if relevant and server_mode and CloudDatabase.is_enabled():
        await run_in_threadpool(CloudDatabase.ensure_fresh, 30)
    response = await call_next(request)
    if relevant and request.method not in ("GET", "HEAD", "OPTIONS") and CloudDatabase.is_enabled():
        await run_in_threadpool(CloudDatabase.after_write)
    return response


app.middleware("http")(cloud_db_middleware)

from infrastructure.security.api_auth import auth_middleware, local_guard_middleware
app.middleware("http")(auth_middleware)
# Unauthenticated local server only accepts loopback hosts and same-origin writes
app.middleware("http")(local_guard_middleware)


async def security_headers_middleware(request, call_next):
    """Baseline browser protections on every response (including errors from the guards)."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    # Pages may only be framed by the site itself (clickjacking); srcdoc frames are unaffected
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
    return response


app.middleware("http")(security_headers_middleware)  # outermost

# Data routes of the web front end (competitions, coaches, HelloAsso links, members): src/api/
from api.competitions import coaches, competitions, helloasso_items, participants
from api.competitions import members as competition_members
from api.competitions import payments, results
from api.activities import planning, presence
from api.communications import attestations, email, whatsapp
from api.members import dashboard, members, seasons
from api.reports import map as members_map, pivot
from api.web import health, pages, pwa
from api.responses import internal_error, service_error_handler
from services.errors import ServiceError
for _api in (competitions, participants, coaches, competition_members, helloasso_items,
             results, payments, members, seasons, dashboard, email, whatsapp, attestations,
             planning, presence, members_map, pivot,
             pages, pwa, health):
    app.include_router(_api.router)
pages.mount_static(app)
# Every route of these routers skips the SQLite cache refresh: a route that reads or writes the
# cache (members, app settings, HelloAsso payments…) must live in another router, even under
# /api/competitions (results batch, check-all-paid).
FIRESTORE_ONLY_PATHS.extend(r.path_regex for _api in (competitions, participants, coaches, competition_members, helloasso_items)
                            for r in _api.router.routes if isinstance(r, APIRoute))
app.add_exception_handler(ServiceError, service_error_handler)

# No CORS: every page calls the API from its own origin. Allowing other origins would let any
# website read the local (unauthenticated) desktop server.

# --------------------------------------------------------------------------
# Micro-service Cloud & Mobile : Webhooks HelloAsso
# --------------------------------------------------------------------------
from infrastructure.helloasso.webhook import HelloAssoWebhookService


@app.get("/webhooks/helloasso")
def webhook_helloasso_ping():
    """Répond aux vérifications de connectivité HelloAsso (ping HTTP 200)."""
    return {
        "status": "active",
        "endpoint": "helloasso-webhook-receiver",
        "supported_events": ["Payment", "Order"],
        "timestamp": datetime.datetime.now().isoformat()
    }


@app.post("/webhooks/helloasso")
async def webhook_helloasso(payload: Dict[str, Any] = Body(...),
                            token: Optional[str] = Query(None)):
    """Point de terminaison Webhook pour les notifications HelloAsso (Payment & Order).
    Réconcilie en temps réel le paiement avec les participants de la compétition.

    Authenticité : jeton secret dans l'URL (?token=...) et/ou relecture des articles
    auprès de l'API HelloAsso (voir HelloAssoWebhookService.handle_notification).
    """
    from infrastructure.firestore.client import FirestoreError
    from infrastructure.helloasso.webhook import WebhookRejected
    from services.competitions.store import invalidate_cache
    if not isinstance(token, str):  # appel direct de la fonction (tests)
        token = None
    try:
        return HelloAssoWebhookService.handle_notification(payload, token=token)
    except WebhookRejected as e:
        print(f"⛔ [WEBHOOK_HELLOASSO] Notification refusée ({e.status_code}) : {e.message}")
        return JSONResponse({"status": "rejected", "message": e.message}, status_code=e.status_code)
    except FirestoreError as e:
        # Firestore unreadable (member list, competitions): nothing could be matched nor
        # recorded. An error status, not 200, so that the failure shows on HelloAsso's side.
        return JSONResponse({"status": "error", "message": internal_error(e, "webhook_helloasso")}, status_code=503)
    except Exception as e:
        return {"status": "error", "message": internal_error(e, "webhook_helloasso")}
    finally:
        invalidate_cache()  # payments recorded on competition documents directly


@app.post("/api/helloasso/sync")
def sync_helloasso_api():
    """Synchronise la campagne annuelle HelloAsso vers Firestore."""
    from services.competitions.store import invalidate_cache
    try:
        from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
        from domain.competitions import matching as competition_matching

        slug = Repo.get_app_setting("HELLOASSO_ANNUAL_CAMPAIGN")
        if not (slug or "").strip():
            return {"status": "error", "message": "Aucune campagne annuelle configurée. Veuillez configurer le slug de la campagne."}

        ident = competition_matching.parse_campaign_identifier(slug)
        from infrastructure.helloasso.api import get_items
        items = get_items(ident["form_type"], ident["slug"]) or []
        summarized = competition_matching.summarize_items(items)

        Repo.sync_helloasso_mirror(summarized, items, ident["slug"])

        competitions = [{"id": c.id, "id_ffme": c.id_ffme, "nom": c.nom}
                        for c in Repo.list_competitions()]
        adherents = Repo.list_adherents()
        existing = Repo.list_helloasso_links()
        links = competition_matching.auto_link_items(summarized, competitions, adherents, existing)
        Repo.replace_auto_links(links)

        applied = Repo.apply_links_to_participants()
        unlinked = Repo.list_unlinked_items()

        return {
            "status": "success",
            "stats": {
                "nb_items": len(items),
                "nb_auto": len([lk for lk in (links or {}).values() if lk]),
                "nb_manual": len([e for e in existing.values() if e.get("source") == "manuel"]),
                "nb_applied": applied,
                "nb_unlinked": len(unlinked),
            }
        }
    except Exception as e:
        return {"status": "error", "message": internal_error(e, "sync_helloasso_api")}
    finally:
        invalidate_cache()  # payments recorded on competition documents directly


# --------------------------------------------------------------------------
# Export Fédéral FFME (CSV)
# --------------------------------------------------------------------------
@app.get("/api/ffme/stats")
def get_ffme_stats_api(season: Optional[str] = None):
    """Calcule et renvoie les statistiques de l'export fédéral FFME."""
    try:
        import datetime
        from infrastructure.sqlite.repository import SqliteRepository
        from domain.constants import get_active_season
        from exports.membership_excel import parse_date_to_datetime, clean_digits_only

        target_season = season or get_active_season()
        participants = SqliteRepository.load_direct_data(season_filter=target_season)

        produced_count = 0
        ignored_count = 0
        termine_count = 0
        renewals_count = 0
        new_licences_count = 0
        ignored_details = []

        now = datetime.datetime.now()

        for p in participants:
            tarif_name = str(p.get("tarif_name") or "").lower()
            amount = p.get("amount", 0.0)
            status = str(p.get("status") or "").lower()
            commentaires = str(p.get("commentaires_correctif") or "").lower()
            is_manual = "ajout manuel" in commentaires

            # 1. Ignoré (liste d'attente, montant nul non manuel, annulé)
            if "attente" in tarif_name or (amount == 0.0 and not is_manual) or "annul" in status or "cancel" in status:
                ignored_count += 1
                continue

            # 2. Date de naissance manquante ou invalide
            dob_val = p.get("birth_date") or p.get("champ_Date de naissance de l'adhérent") or ""
            dob_date = None
            if isinstance(dob_val, (datetime.datetime, datetime.date)):
                dob_date = dob_val
            else:
                parsed_dt = parse_date_to_datetime(str(dob_val).strip())
                if isinstance(parsed_dt, (datetime.datetime, datetime.date)):
                    dob_date = parsed_dt

            if not dob_date or dob_date >= now:
                ignored_count += 1
                nom = str(p.get("last_name") or "Inconnu").strip().upper()
                prenom = str(p.get("first_name") or "Inconnu").strip()
                ignored_details.append(f"{nom} {prenom} (date de naissance manquante/invalide)")
                continue

            # 3. Terminé ou à produire
            lic = clean_digits_only(p.get("licence_ffme") or "")
            is_renewal = 5 <= len(lic) <= 10

            if "termin" in status:
                termine_count += 1
            else:
                produced_count += 1

            if is_renewal:
                renewals_count += 1
            else:
                new_licences_count += 1

        return {
            "status": "success",
            "season": target_season,
            "produced_count": produced_count,
            "termine_count": termine_count,
            "ignored_count": ignored_count,
            "estimated_total": produced_count + termine_count,
            "renewals_count": renewals_count,
            "new_licences_count": new_licences_count,
            "ignored_details": ignored_details[:20]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "get_ffme_stats_api")})


@app.get("/api/ffme/export")
def export_ffme_api(season: Optional[str] = None, include_termine: bool = Query(True)):
    """Génère le fichier CSV d'import FFME et le renvoie directement en téléchargement."""
    import os
    import tempfile
    import datetime
    from infrastructure.sqlite.repository import SqliteRepository
    from domain.constants import get_active_season
    from exports.membership_excel import generate_ffme_csv

    try:
        target_season = season or get_active_season()
        raw_data = SqliteRepository.load_direct_data(season_filter=target_season)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"import_ffme_{timestamp}.csv"
        
        tmp_dir = tempfile.mkdtemp(prefix="alj_ffme_export_")
        tmp_csv = os.path.join(tmp_dir, filename)

        try:
            ignored = generate_ffme_csv(raw_data, output_path=tmp_csv, include_termine=include_termine)
            with open(tmp_csv, "rb") as f:
                content_bytes = f.read()

            return Response(
                content=content_bytes,
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Access-Control-Expose-Headers": "Content-Disposition"
                }
            )
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "export_ffme_api")})


# --------------------------------------------------------------------------
# Importation & Rapprochement Fédéral FFME (Excel)
# --------------------------------------------------------------------------
@app.post("/api/ffme/preview")
def preview_ffme_import_api(data: Dict[str, Any] = Body(...)):
    """Analyse un fichier Excel FFME et prépare le rapprochement sans modifier la base."""
    import base64
    import tempfile
    import os
    from infrastructure.sqlite.repository import SqliteRepository

    try:
        content_b64 = data.get("content_base64") or ""
        filename = str(data.get("filename") or "licencies_ffme.xlsx").strip()

        if not content_b64:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Fichier Excel manquant (content_base64 obligatoire)."})

        file_bytes = base64.b64decode(content_b64)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            prep = SqliteRepository.prepare_ffme_licensees(tmp_path)
            stats = prep.get("stats", {})
            if stats.get("errors") and not prep.get("updates"):
                return JSONResponse(status_code=400, content={"status": "error", "message": stats["errors"][0], "errors": stats["errors"]})

            return {
                "status": "success",
                "filename": filename,
                "stats": stats,
                "matched_count": len(prep.get("updates", [])),
                "unmatched_count": len(prep.get("unmatched", [])),
                "updates": prep.get("updates", []),
                "unmatched": prep.get("unmatched", []),
                "users": prep.get("users", [])
            }
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "preview_ffme_import_api")})


@app.post("/api/ffme/import")
def apply_ffme_import_api(data: Dict[str, Any] = Body(...)):
    """Applique l'importation FFME en BDD (mises à jour automatiques + associations manuelles)."""
    import base64
    import os
    import tempfile
    from infrastructure.sqlite.repository import SqliteRepository
    from domain.constants import get_active_season
    from paths import ROOT_DIR

    try:
        season = str(data.get("season") or get_active_season()).strip()
        updates = list(data.get("updates") or [])
        manual_matches = list(data.get("manual_matches") or [])
        content_b64 = data.get("content_base64")
        filename = str(data.get("filename") or "import_ffme.xlsx").strip()

        # Si pas d'updates fournis mais content_b64 fourni : préparer automatiquement
        stats = {
            "total_processed": 0,
            "matched_by_licence": 0,
            "matched_by_name": 0,
            "matched_manually": 0,
            "errors": []
        }

        if not updates and content_b64:
            file_bytes = base64.b64decode(content_b64)
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                prep = SqliteRepository.prepare_ffme_licensees(tmp_path)
                updates = prep.get("updates", [])
                stats = prep.get("stats", {})
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        elif data.get("stats"):
            stats = dict(data.get("stats"))

        # Ajouter les associations manuelles
        matched_manually = 0
        for m in manual_matches:
            uid = m.get("user_id")
            if uid:
                updates.append((
                    "Terminé",
                    str(m.get("licence") or "").strip(),
                    str(m.get("passeports") or "").strip(),
                    str(m.get("diplomes") or "").strip(),
                    str(m.get("document_sante") or "").strip(),
                    int(uid)
                ))
                matched_manually += 1

        stats["matched_manually"] = matched_manually

        if not updates:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Aucune mise à jour à appliquer (aucun rapprochement trouvé)."}
            )

        ok = SqliteRepository.apply_ffme_matches(updates, season_name=season)
        if not ok:
            return JSONResponse(status_code=500, content={"status": "error", "message": "Échec de l'écriture des associations en base de données."})

        # Sauvegarde éventuelle d'une copie dans import/ffme/
        if content_b64:
            try:
                dest_dir = os.path.join(ROOT_DIR, "import", "ffme")
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, filename)
                file_bytes = base64.b64decode(content_b64)
                with open(dest_path, "wb") as f:
                    f.write(file_bytes)
            except Exception as se:
                print(f"[FFME IMPORT] Copie locale du fichier non critique : {se}")

        from infrastructure.firestore.cloud_database import CloudDatabase
        if CloudDatabase.is_enabled():
            CloudDatabase.after_write()

        return {
            "status": "success",
            "message": f"Importation FFME validée : {len(updates)} adhérents mis à jour.",
            "updated_count": len(updates),
            "matched_manually": matched_manually,
            "season": season,
            "stats": stats
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "apply_ffme_import_api")})


# --------------------------------------------------------------------------
# Renouvellement et Gestion OAuth2 Google (Gmail API, Drive & Firestore)
# --------------------------------------------------------------------------
@app.get("/api/auth/google/status")
def get_google_auth_status():
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
            error_msg = str(e)
            
    db_ready = CloudDatabase.cache_ready() if CloudDatabase.is_enabled() else False

    status = "connected" if valid else ("expired" if refresh_token else "disconnected")

    return {
        "status": status,
        "valid": valid,
        "configured": configured,
        "client_id_configured": bool(client_id),
        "refresh_token_present": bool(refresh_token),
        "user_email": user_email,
        "backend": backend,
        "db_accessible": db_ready or valid,
        "error": error_msg,
    }


@app.get("/api/auth/google/login")
def google_auth_login(request: Request, return_to: Optional[str] = "/bureau/parametres", redirect_uri: Optional[str] = None):
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
        "return_to": return_to or "/bureau/parametres",
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


@app.get("/api/auth/google/callback", response_class=HTMLResponse)
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

    def _render_page(title: str, body_html: str, return_url: str = "/bureau/parametres", auto_redirect: bool = False):
        redirect_script = f"<script>setTimeout(function() {{ window.location.href = '{return_url}'; }}, 3500);</script>" if auto_redirect else ""
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
            <div class="badge badge-error">Erreur : {error}</div>
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
    return_to = "/bureau/parametres"
    redirect_uri = ""
    if state:
        try:
            raw_state = base64.urlsafe_b64decode(state.encode("utf-8")).decode("utf-8")
            state_data = json.loads(raw_state)
            return_to = state_data.get("return_to", "/bureau/parametres")
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
        return _render_page(
            "Erreur réseau",
            f"""<h2>❌ Échec de la communication avec Google</h2>
            <div class="badge badge-error">Erreur de connexion</div>
            <p>{str(e)}</p>
            <p><a href="/bureau/outils" class="btn">Retour au bureau</a></p>"""
        )

    if token_resp.status_code != 200:
        err_detail = token_resp.text
        return _render_page(
            "Échec d'échange de jeton",
            f"""<h2>❌ Échange de jeton échoué</h2>
            <div class="badge badge-error">HTTP {token_resp.status_code}</div>
            <p>Google a refusé l'échange du code d'autorisation :</p>
            <div class="details"><pre style="margin:0; white-space:pre-wrap;">{err_detail}</pre></div>
            <p><b>Vérification conseillée :</b> assurez-vous que l'URI de redirection suivante est bien autorisée dans votre Google Cloud Console :<br>
            <code>{redirect_uri}</code></p>
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
    sync_err = ""
    if CloudDatabase.is_enabled():
        try:
            CloudDatabase.sync()
        except Exception as se:
            sync_ok = False
            sync_err = str(se)

    email_display = f"Compte connecté : <b>{user_email}</b>" if user_email else "Compte Google connecté"
    sync_display = "✅ Base de données synchronisée avec succès." if sync_ok else f"⚠️ Connexion rétablie, mais synchro en attente : {sync_err}"

    return _render_page(
        "Connexion Réussie",
        f"""<h2>🎉 Connexion Google Réussie !</h2>
        <div class="badge badge-success">Accès BDD & Gmail rétabli</div>
        <p>{email_display}</p>
        <p>{sync_display}</p>
        <details style="margin:16px 0; text-align:left; font-size:12px; background:#F8FAFC; border:1px solid #CBD5E1; border-radius:8px; padding:10px 12px;">
            <summary style="cursor:pointer; font-weight:600; color:#334155;">🔑 Nouveau Refresh Token (pour Cloud Run)</summary>
            <p style="margin:6px 0 4px; color:#64748B; font-size:11.5px;">Le jeton a été synchronisé. Vous pouvez également copier cette valeur dans Cloud Run (GMAIL_REFRESH_TOKEN) :</p>
            <input type="text" readonly value="{refresh_token}" style="width:100%; box-sizing:border-box; padding:6px 8px; font-family:monospace; font-size:11px; background:#FFF; border:1px solid #CBD5E1; border-radius:4px;" onclick="this.select();">
        </details>
        <p style="font-size:13px; color:#64748B;">Redirection automatique vers le bureau dans quelques secondes…</p>
        <p><a href="{return_to}" class="btn">Retourner au bureau immédiatement</a></p>""",
        return_url=return_to,
        auto_redirect=True
    )


@app.post("/api/auth/google/test")
def test_google_auth():
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
        results["oauth_token"]["message"] = f"Échec de renouvellement OAuth2 : {e}"
        results["database"]["message"] = "Test BDD ignoré en raison de l'échec OAuth2."
        results["gmail"]["message"] = "Test Gmail ignoré en raison de l'échec OAuth2."
        return {"status": "error", "all_ok": False, "results": results}

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
        results["database"]["message"] = f"Erreur d'accès à la BDD : {e}"

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
        results["gmail"]["message"] = f"Erreur lors du test Gmail : {e}"

    all_ok = all(r["ok"] for r in results.values())
    return {
        "status": "success" if all_ok else "warning",
        "all_ok": all_ok,
        "results": results
    }


@app.post("/api/auth/google/update-token")
def update_google_token(data: Dict[str, Any] = Body(...)):
    """Permet à un administrateur de renseigner ou forcer un refresh token manuellement."""
    import requests
    from infrastructure.google.drive import GoogleDriveClient
    from infrastructure.firestore.cloud_database import CloudDatabase
    
    refresh_token = str(data.get("refresh_token") or "").strip()
    client_id = str(data.get("client_id") or "").strip()
    client_secret = str(data.get("client_secret") or "").strip()
    user_email = str(data.get("user_email") or "").strip()

    if not refresh_token:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Le refresh token est requis."})

    cid_exist, sec_exist = GoogleDriveClient.get_client_credentials()
    final_cid = client_id or cid_exist
    final_sec = client_secret or sec_exist

    if not final_cid or not final_sec:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Client ID ou Client Secret manquant."})

    test_data = {
        "client_id": final_cid,
        "client_secret": final_sec,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data=test_data, timeout=15)
        if r.status_code != 200:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": f"Google a rejeté ce jeton : {r.text}"}
            )
        access_tok = r.json().get("access_token")
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Impossible de joindre Google : {e}"}
        )

    if not user_email and access_tok:
        try:
            u_resp = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_tok}"},
                timeout=10
            )
            if u_resp.status_code == 200:
                user_email = u_resp.json().get("email", "")
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

    return {
        "status": "success",
        "message": "Jeton Google mis à jour et validé avec succès.",
        "user_email": user_email
    }


@app.get("/api/cloud-db/status")
def get_cloud_db_status_api():
    """Retourne l'état détaillé du cache local SQLite et de sa synchronisation Firestore."""
    try:
        from infrastructure.firestore.cloud_database import CloudDatabase
        from infrastructure.sqlite.repository import SqliteRepository
        enabled = CloudDatabase.is_enabled()
        st = CloudDatabase.status() if enabled else {}
        db_path = SqliteRepository.get_db_path()
        db_exists = os.path.exists(db_path)
        db_size_kb = round(os.path.getsize(db_path) / 1024, 1) if db_exists else 0

        member_count = 0
        if db_exists:
            try:
                conn = SqliteRepository.get_connection()
                row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
                member_count = row[0] if row else 0
                conn.close()
            except Exception:
                pass

        return {
            "status": "success",
            "enabled": enabled,
            "db_exists": db_exists,
            "db_filename": os.path.basename(db_path),
            "db_size_kb": db_size_kb,
            "member_count": member_count,
            "pending": st.get("pending", 0),
            "last_error": st.get("last_error", ""),
            "last_sync": st.get("last_sync"),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "get_cloud_db_status_api")})


@app.post("/api/cloud-db/sync")
def sync_cloud_db_api(force: bool = Query(False)):
    """Force la synchronisation bilatérale entre Firestore et la base SQLite locale."""
    try:
        from infrastructure.firestore.cloud_database import CloudDatabase
        if not CloudDatabase.is_enabled():
            return {"status": "skipped", "message": "Mode Firestore non activé (MEMBER_BACKEND != firestore)."}

        result = CloudDatabase.sync(full=force, force_pull_all=force)
        errors = result.get("errors") if isinstance(result, dict) else []
        if errors:
            return JSONResponse(status_code=500, content={"status": "error", "message": f"Erreur de synchronisation : {'; '.join(errors)}", "result": result})

        return {
            "status": "success",
            "message": "Base de données SQLite synchronisée avec succès avec Firestore.",
            "result": result
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "sync_cloud_db_api")})


if __name__ == "__main__":
    import uvicorn
    # Support de la variable d'environnement PORT (Cloud Run injecte PORT=8080)
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    uvicorn.run("server:app", host=host, port=port, reload=(port == 8000))
