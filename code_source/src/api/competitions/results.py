"""MyCompet FFME results: daily batch (Cloud Scheduler), fetch for one competition, batch settings.

The batch settings and status now live in Firestore (app_settings): these routes no longer read the
SQLite cache. Moving this router to the Firestore-only list of server.py (no cache refresh before the
batch) is a separate change.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from api.competitions.schemas.results import BatchReport, ResultsSettings, ResultsSettingsSaved, ResultsSettingsUpdate
from api.competitions.schemas.views import ResultsFetched
from api.responses import error, error_responses

# Full paths: /api/competitions/... and /api/settings/...
router = APIRouter()



# Batch quotidien de récupération des résultats MyCompet FFME & Notifications.
# Stays registered before /{comp_id}/fetch-results, which would capture "cron": Cloud Scheduler
# (job batch-resultats-competitions) calls POST /api/competitions/cron/fetch-results every day.
@router.post("/api/competitions/cron/fetch-results", response_model=BatchReport, responses=error_responses(403, 503))
async def api_cron_fetch_competition_results(
    request: Request,
    force: bool = False,
    email: Optional[str] = None
) -> BatchReport | JSONResponse:
    """
    Exécute le batch de récupération des résultats MyCompet FFME pour les compétitions passées
    et envoie un e-mail de synthèse si des résultats sont découverts.
    Called by Cloud Scheduler every day at 07:00 (its OIDC token, see api_auth.SCHEDULER_PATHS) or by an admin.
    `force` (every ended competition, results or not) and `email` (another recipient): admin only.
    503: the competitions could not be read, nothing was done (Cloud Scheduler shows the run as failed).
    """
    from infrastructure.security.api_auth import Role, has_role, is_scheduler
    from services.competitions.results_batch import CompetitionResultsBatchService, ResultsBatchError
    from services.competitions.store import invalidate_cache
    claims = getattr(request.state, "user", None)  # None: token check off (local server)
    is_admin = claims is None or (not is_scheduler(claims) and has_role(claims, Role.ADMIN))
    if (force or email) and not is_admin:
        return error(403, "Les options force et email sont réservées aux administrateurs.")
    try:
        report = await run_in_threadpool(CompetitionResultsBatchService.run_daily_batch, force=force, to_email=email)
        return BatchReport.model_validate(report)
    except ResultsBatchError:
        return error(503, "Lecture des compétitions impossible : le batch n'a rien fait (détails dans les journaux).")
    finally:
        invalidate_cache()  # the batch writes competition documents directly


@router.post("/api/competitions/{comp_id}/fetch-results", response_model=ResultsFetched, responses=error_responses(404, 502))
async def api_fetch_competition_results(comp_id: str, payload: Dict[str, Any] = Body(default={})) -> ResultsFetched | JSONResponse:  # Any: {url, club}
    """
    Récupère les résultats officiels depuis MyCompet FFME pour une compétition donnée,
    extrait les compétiteurs de l'Amicale Laïque de Jonage et met à jour leurs classements.
    404 `needs_url`: the results page was not found automatically, the coach gives its address or number.
    """
    from infrastructure.mycompet.scraper import fetch_and_parse_mycompet_results, normalize_result_url, find_mycompet_result_url
    from infrastructure.firestore.client import FirestoreClient, FirestoreError

    url = (payload.get("url") or payload.get("result_id") or "").strip()

    comp_doc = None
    try:
        comp_doc = FirestoreClient.get_document("competitions", comp_id)
    except Exception as e:
        print(f"⚠️ [MYCOMPET] Impossible de lire la compétition {comp_id} sur Firestore : {e}")

    if not url and comp_doc:
        url = comp_doc.get("url_resultats") or comp_doc.get("id_resultat_ffme") or ""

    # Détection automatique transparente si aucune URL n'est renseignée
    if not url and comp_doc:
        nom = comp_doc.get("nom") or ""
        date = comp_doc.get("date_competition") or ""
        lieu = comp_doc.get("lieu") or ""
        id_ffme = comp_doc.get("id_ffme") or ""
        date_fin = comp_doc.get("date_fin") or ""
        auto_url = await run_in_threadpool(find_mycompet_result_url, nom, date, lieu, str(id_ffme), date_fin)
        if auto_url:
            url = auto_url

    if not url:
        return error(404, "Résultats introuvables automatiquement sur MyCompet. Veuillez renseigner l'URL ou le numéro de "
                          "résultat (ex: https://mycompet.ffme.fr/resultat/resultat_13660 ou 13660).", "needs_url")

    try:
        club_kw = payload.get("club") or "JONAGE"
        scraped_results = await run_in_threadpool(fetch_and_parse_mycompet_results, url, club_kw)
    except Exception as e:
        print(f"❌ [MYCOMPET] Erreur scraping MyCompet ({url}) : {type(e).__name__}: {e}")
        return error(502, "Erreur lors de la récupération des résultats MyCompet (détails dans les journaux).")

    now_iso = datetime.datetime.now().isoformat()
    canonical_url = normalize_result_url(url)
    matched_count = 0
    if comp_doc:
        from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository
        from services.competitions.results_batch import apply_rankings
        fields = {"url_resultats": canonical_url, "resultats_synced_at": now_iso}
        try:
            # Re-read and written under the optimistic lock: an edit made meanwhile on the web is kept
            matched_count = await run_in_threadpool(
                CompetitionFirestoreRepository.record_results, comp_doc.get("id") or comp_id,
                lambda parts: len(apply_rankings(parts, scraped_results, now_iso)), fields)
            if not matched_count:  # keep the URL the coach gave, for the next try
                FirestoreClient.update_fields("competitions", comp_doc.get("_doc_id") or comp_id, fields)
        except FirestoreError as e:
            print(f"⚠️ [MYCOMPET] Erreur mise à jour Firestore : {e}")
        finally:
            from services.competitions.store import invalidate_cache
            invalidate_cache()  # results visible on the next poll of the competition pages

    return ResultsFetched(status="success", url=canonical_url, total_scraped=len(scraped_results), matched_count=matched_count)


@router.get("/api/settings/competitions-results", response_model=ResultsSettings)
def get_competitions_results_settings_api() -> ResultsSettings:
    """Retourne la configuration et l'état du batch quotidien de résultats."""
    from services.competitions.results_batch import CompetitionResultsBatchService
    return ResultsSettings(status="success", **CompetitionResultsBatchService.get_batch_status())


@router.post("/api/settings/competitions-results", response_model=ResultsSettingsSaved, responses=error_responses(400))
def update_competitions_results_settings_api(data: ResultsSettingsUpdate) -> ResultsSettingsSaved | JSONResponse:
    """Met à jour les adresses e-mail de notification des résultats (et la fenêtre de recherche, si fournie)."""
    from services.competitions.results_batch import CompetitionResultsBatchService
    if data.window_days is not None and not 1 <= data.window_days <= 365:
        return error(400, "Fenêtre de recherche invalide : entre 1 et 365 jours.")
    try:
        ok = CompetitionResultsBatchService.set_notification_email(data.notification_email)
    except ValueError as e:
        return error(400, str(e))

    if data.window_days is not None:
        ok = CompetitionResultsBatchService.set_window_days(data.window_days) and ok
    return ResultsSettingsSaved(status="success", notification_email=CompetitionResultsBatchService.get_notification_email(),
                                window_days=CompetitionResultsBatchService.get_window_days(), saved=ok)
