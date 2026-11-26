"""E-mail log of the whole app: the latest sends, for Communications › Historique des envois.

Admin only (under /api/admin: api_auth.required_role). Firestore only (server.py FIRESTORE_ONLY_PATHS).
"""

from __future__ import annotations

from fastapi import APIRouter

from api.communications.schemas import RecentEmailLog
from api.responses import STORAGE_ERRORS, error_responses
from services.communications import email_log

router = APIRouter(prefix="/api/admin")


@router.get("/email-log", response_model=RecentEmailLog, responses=error_responses(*STORAGE_ERRORS))
def recent_email_log() -> RecentEmailLog:
    return RecentEmailLog.model_validate(email_log.recent_history())
