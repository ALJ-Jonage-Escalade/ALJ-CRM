"""HelloAsso payments of a competition: notification once every participant has paid.

Reads the SQLite cache (the competition repository's member projection): must not join the Firestore-only routers of server.py.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.competitions.schemas.views import AllPaidChecked
from api.responses import error_responses
from services.competitions.all_paid_notification import check_and_notify_all_paid

router = APIRouter(prefix="/api/competitions")


@router.post("/{comp_id}/check-all-paid", response_model=AllPaidChecked, responses=error_responses(500, 503))
def check_competition_all_paid_api(comp_id: int) -> AllPaidChecked:
    """Vérifie si tous les compétiteurs ont payé et envoie l'e-mail récapitulatif si applicable."""
    notified = check_and_notify_all_paid(comp_id)
    return AllPaidChecked(status="success", competition_id=comp_id, notified=bool(notified))
