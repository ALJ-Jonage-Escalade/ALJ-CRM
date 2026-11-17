"""E-mail log of a competition: what was sent about it, when, by whom and to whom (readonly and above).

Firestore only (server.py FIRESTORE_ONLY_PATHS): never waits for the SQLite cache.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.competitions.schemas.email_log import CompetitionEmailLog
from api.responses import STORAGE_ERRORS, error_responses
from services.communications import email_log

router = APIRouter(prefix="/api/competitions")


@router.get("/{competition_id}/email-log", response_model=CompetitionEmailLog, responses=error_responses(404, *STORAGE_ERRORS))
def competition_email_log(competition_id: int) -> CompetitionEmailLog:
    return CompetitionEmailLog.model_validate(email_log.competition_history(competition_id))
