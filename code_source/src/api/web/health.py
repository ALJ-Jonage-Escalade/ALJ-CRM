"""Health check (Cloud Run probes, deploy smoke test)."""

from __future__ import annotations

import datetime

from fastapi import APIRouter

from domain.constants import APP_VERSION, get_active_season

router = APIRouter()


@router.get("/health")
def health_check():
    """Vérification de santé (Cloud Run probes, uptime, monitoring)."""
    return {
        "status": "healthy",
        "service": "alj-escalade-api",
        "version": APP_VERSION,
        "season": get_active_season(),
        "timestamp": datetime.datetime.now().isoformat()
    }
