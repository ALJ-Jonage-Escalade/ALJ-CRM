"""HelloAsso: payment webhook (public, its own authenticity checks) and annual campaign sync.

HelloAsso always calls the main URL (production revision): keep /webhooks/helloasso as it is.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from api.integrations.schemas import HelloAssoSync, HelloAssoSyncStats
from api.responses import STORAGE_ERRORS, error_responses
from domain.errors import Forbidden, UpstreamUnavailable
from services.competitions.helloasso_items import HelloAssoItemService
from services.competitions.helloasso_webhook import HelloAssoWebhookService

logger = logging.getLogger("alj")
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
    auprès de l'API HelloAsso (voir HelloAssoWebhookService.verify_and_reconcile_notification).
    A refusal answers 401 (token) or 503 (not checkable now: HelloAsso sends the notification again later). Any other
    failure is never answered 200, so that it shows on HelloAsso's side: 503 when Firestore failed, else 500
    (api.responses: service_error_handler, unhandled_error_middleware).
    """
    try:
        return HelloAssoWebhookService.verify_and_reconcile_notification(payload, token=token)
    except (Forbidden, UpstreamUnavailable) as rejection:
        status_code = 401 if isinstance(rejection, Forbidden) else 503
        logger.warning("[WEBHOOK_HELLOASSO] Notification refusée (%s) : %s", status_code, rejection.message)
        return JSONResponse({"status": "rejected", "message": rejection.message, "code": rejection.code}, status_code=status_code)


@router.post("/api/helloasso/sync", response_model=HelloAssoSync, responses=error_responses(400, 502, *STORAGE_ERRORS))
def sync_helloasso_api() -> HelloAssoSync:
    """Reads the competitions' HelloAsso campaign and links its payments (mirror, automatic links, participants).
    400 `no_campaign`: no campaign chosen; 502: HelloAsso could not be read completely, nothing is written;
    503: Firestore unavailable."""
    return HelloAssoSync(status="success", stats=HelloAssoSyncStats(**HelloAssoItemService.sync_campaign()))
