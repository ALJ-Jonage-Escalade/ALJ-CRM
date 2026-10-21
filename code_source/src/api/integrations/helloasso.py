"""HelloAsso: payment webhook (public, its own authenticity checks) and annual campaign sync.

HelloAsso always calls the main URL (production revision): keep /webhooks/helloasso as it is.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from api.responses import internal_error
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


@router.post("/api/helloasso/sync")
def sync_helloasso_api():
    """Synchronise la campagne annuelle HelloAsso vers Firestore."""
    from services.competitions.store import invalidate_cache
    try:
        from infrastructure.firestore.app_settings import AppSettingsRepository
        from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
        from domain.competitions import matching as competition_matching

        slug = AppSettingsRepository.get("HELLOASSO_ANNUAL_CAMPAIGN")
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
