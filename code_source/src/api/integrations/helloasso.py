"""HelloAsso: payment webhook (public, its own authenticity checks) and annual campaign sync.

HelloAsso always calls the main URL (production revision): keep /webhooks/helloasso as it is.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from api.competitions.schemas.views import HelloAssoSync, HelloAssoSyncStats
from api.responses import STORAGE_ERRORS, error_responses, internal_error
from infrastructure.firestore.client import FirestoreError
from services.competitions.helloasso_items import HelloAssoItemService
from services.competitions.helloasso_webhook import HelloAssoWebhookService, WebhookRejected
from services.competitions.store import invalidate_cache

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
    """
    try:
        return HelloAssoWebhookService.verify_and_reconcile_notification(payload, token=token)
    except WebhookRejected as e:
        logger.warning("[WEBHOOK_HELLOASSO] Notification refusée (%s) : %s", e.status_code, e.message)
        return JSONResponse({"status": "rejected", "message": e.message}, status_code=e.status_code)
    except FirestoreError as e:
        # Firestore unreadable (member list, competitions, settings): nothing could be matched nor
        # recorded. An error status, not 200, so that the failure shows on HelloAsso's side.
        return JSONResponse({"status": "error", "message": internal_error(e, "webhook_helloasso")}, status_code=503)
    except Exception as e:  # any other failure, possibly midway: an error status too, never 200
        return JSONResponse({"status": "error", "message": internal_error(e, "webhook_helloasso")}, status_code=500)
    finally:
        invalidate_cache()  # the webhook writes competition documents outside the @write services


@router.post("/api/helloasso/sync", response_model=HelloAssoSync, responses=error_responses(400, 502, *STORAGE_ERRORS))
def sync_helloasso_api() -> HelloAssoSync:
    """Reads the competitions' HelloAsso campaign and links its payments (mirror, automatic links, participants).
    400 `no_campaign`: no campaign chosen; 502: HelloAsso could not be read completely, nothing is written;
    503: Firestore unavailable."""
    return HelloAssoSync(status="success", stats=HelloAssoSyncStats(**HelloAssoItemService.sync_campaign()))
