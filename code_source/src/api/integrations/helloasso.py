"""HelloAsso: payment webhook (public, its own authenticity checks) and annual campaign sync.

HelloAsso always calls the main URL (production revision): keep /webhooks/helloasso as it is.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from api.competitions.schemas.views import HelloAssoSync, HelloAssoSyncStats
from api.responses import error, error_responses, internal_error
from infrastructure.helloasso.webhook import HelloAssoWebhookService

router = APIRouter()


@router.get("/webhooks/helloasso")
def webhook_helloasso_ping():
    """Répond aux vérifications de connectivité HelloAsso (ping HTTP 200)."""
    return {
        "status": "active",
        "endpoint": "helloasso-webhook-receiver",
        "supported_events": ["Payment", "Order"],
        "timestamp": datetime.datetime.now().isoformat()
    }


@router.post("/webhooks/helloasso")
def webhook_helloasso(payload: Dict[str, Any] = Body(...),  # Any: HelloAsso's notification, checked by the service
                      token: Optional[str] = Query(None)):
    """Point de terminaison Webhook pour les notifications HelloAsso (Payment & Order).
    Réconcilie en temps réel le paiement avec les participants de la compétition.

    Authenticité : jeton secret dans l'URL (?token=...) et/ou relecture des articles
    auprès de l'API HelloAsso (voir HelloAssoWebhookService.handle_notification).
    """
    from infrastructure.firestore.client import FirestoreError
    from infrastructure.helloasso.webhook import WebhookRejected
    from services.competitions.store import invalidate_cache
    try:
        return HelloAssoWebhookService.handle_notification(payload, token=token)
    except WebhookRejected as e:
        print(f"⛔ [WEBHOOK_HELLOASSO] Notification refusée ({e.status_code}) : {e.message}")
        return JSONResponse({"status": "rejected", "message": e.message}, status_code=e.status_code)
    except FirestoreError as e:
        # Firestore unreadable (member list, competitions, settings): nothing could be matched nor
        # recorded. An error status, not 200, so that the failure shows on HelloAsso's side.
        return JSONResponse({"status": "error", "message": internal_error(e, "webhook_helloasso")}, status_code=503)
    except Exception as e:  # any other failure, possibly midway: an error status too, never 200
        return JSONResponse({"status": "error", "message": internal_error(e, "webhook_helloasso")}, status_code=500)
    finally:
        invalidate_cache()  # payments recorded on competition documents directly


@router.post("/api/helloasso/sync", response_model=HelloAssoSync, responses=error_responses(400, 502, 503))
def sync_helloasso_api() -> HelloAssoSync | JSONResponse:
    """Reads the competitions' HelloAsso campaign and links its payments (mirror, automatic links, participants).
    400: no campaign chosen; 502: HelloAsso could not be read completely, nothing is written (a partial read would
    unlink the payments it missed); 503: Firestore unavailable."""
    from domain.competitions import matching as competition_matching
    from infrastructure.firestore.app_settings import HELLOASSO_COMPETITION_CAMPAIGN, AppSettingsRepository
    from infrastructure.firestore.client import FirestoreError
    from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
    from infrastructure.helloasso.api import HelloAssoApiError, fetch_form_items
    from services.competitions.store import invalidate_cache
    try:
        slug = AppSettingsRepository.get(HELLOASSO_COMPETITION_CAMPAIGN)
        if not (slug or "").strip():
            return error(400, "Aucune campagne compétitions choisie : choisissez-la dans Paramètres › Campagne HelloAsso.",
                         "no_campaign")
        try:
            ident = competition_matching.parse_campaign_identifier(slug)
        except ValueError as e:
            return error(400, f"Campagne compétitions inexploitable ({e}) : choisissez-la dans Paramètres › Campagne HelloAsso.",
                         "no_campaign")
        try:
            items = fetch_form_items(ident["form_type"], ident["slug"])
        except HelloAssoApiError as e:
            return error(502, f"{e.message} Rien n'a été modifié.", e.code)
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

        return HelloAssoSync(status="success", stats=HelloAssoSyncStats(
            nb_items=len(items),
            nb_auto=len([lk for lk in (links or {}).values() if lk]),
            nb_manual=len([e for e in existing.values() if e.get("source") == "manuel"]),
            nb_applied=applied,
            nb_unlinked=len(unlinked),
        ))
    except FirestoreError as e:
        return error(503, internal_error(e, "sync_helloasso_api"))
    finally:
        invalidate_cache()  # payments recorded on competition documents directly
