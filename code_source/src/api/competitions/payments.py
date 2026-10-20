"""HelloAsso payments of a competition: notification once every participant has paid.

Reads the SQLite cache (HelloAssoWebhookService): must not join the Firestore-only routers of server.py.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.responses import internal_error

router = APIRouter(prefix="/api/competitions")


@router.post("/{comp_id}/check-all-paid")
def check_competition_all_paid_api(comp_id: int):
    """Vérifie si tous les compétiteurs ont payé et envoie l'e-mail récapitulatif si applicable."""
    try:
        from infrastructure.helloasso.webhook import HelloAssoWebhookService
        notified = HelloAssoWebhookService.check_and_notify_all_paid(comp_id)
        return {
            "status": "success",
            "competition_id": comp_id,
            "notified": notified
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "check_competition_all_paid_api")})
