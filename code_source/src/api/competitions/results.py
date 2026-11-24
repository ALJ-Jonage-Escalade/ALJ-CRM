"""MyCompet FFME results: daily batch (Cloud Scheduler), fetch for one competition, batch settings.

Firestore only (competitions, app_settings): this router is in the Firestore-only list of server.py, so
Cloud Scheduler's call does not wait for a SQLite cache rebuild. A route that reads the cache must go
in another router.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool

from api.competitions.schemas.results import (
    BatchReport, ResultsFetchRequest, ResultsSettings, ResultsSettingsSaved, ResultsSettingsUpdate,
)
from api.competitions.schemas.views import ResultsFetched
from api.responses import error, error_responses
from infrastructure.security.api_auth import Role, has_role, is_scheduler
from services.competitions.results_batch import CompetitionResultsBatchService

# Full paths: /api/competitions/... and /api/settings/...
router = APIRouter()


# Batch quotidien de récupération des résultats MyCompet FFME & Notifications.
# Stays registered before /{competition_id}/fetch-results, which would take "cron" for an id: Cloud Scheduler
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
    `force` (every competition ended in the last year, results or not) and `email` (another recipient): admin only.
    503: the competitions could not be read, nothing was done (Cloud Scheduler shows the run as failed).
    """
    claims = getattr(request.state, "user", None)  # None: token check off (local server)
    is_admin = claims is None or (not is_scheduler(claims) and has_role(claims, Role.ADMIN))
    if (force or email) and not is_admin:
        return error(403, "Les options force et email sont réservées aux administrateurs.")
    report = await run_in_threadpool(CompetitionResultsBatchService.run_daily_batch, force=force, to_email=email)
    return BatchReport.model_validate(report)


@router.post("/api/competitions/{competition_id}/fetch-results", response_model=ResultsFetched,
             responses=error_responses(404, 502, 503))
def api_fetch_competition_results(competition_id: int, data: ResultsFetchRequest) -> ResultsFetched:
    """Fetches a competition's MyCompet results and writes the club's rankings (coaches).
    404 `needs_url`: the results page was not found automatically, the coach gives its address or number;
    502: MyCompet failed; 503: Firestore failed (nothing reported as saved)."""
    fetched = CompetitionResultsBatchService.fetch_results_for(competition_id, data.url, data.club or "JONAGE")
    return ResultsFetched(status="success", **fetched)


@router.get("/api/settings/competitions-results", response_model=ResultsSettings)
def get_competitions_results_settings_api() -> ResultsSettings:
    """Retourne la configuration et l'état du batch quotidien de résultats."""
    return ResultsSettings(status="success", **CompetitionResultsBatchService.get_batch_status())


@router.post("/api/settings/competitions-results", response_model=ResultsSettingsSaved, responses=error_responses(400, 503))
def update_competitions_results_settings_api(data: ResultsSettingsUpdate) -> ResultsSettingsSaved:
    """Met à jour les adresses e-mail de notification des résultats (et la fenêtre de recherche, si fournie).
    400: an address or the window is invalid, nothing is saved; 503: Firestore failed."""
    CompetitionResultsBatchService.update_settings(data.notification_email, data.window_days)
    return ResultsSettingsSaved(status="success", notification_email=CompetitionResultsBatchService.get_notification_email(),
                                window_days=CompetitionResultsBatchService.get_window_days())
