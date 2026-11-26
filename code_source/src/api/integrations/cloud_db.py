"""SQLite cache of the crm_* Firestore collections: status and forced sync."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from api.integrations.schemas import CloudDbStatus, CloudDbSync, SyncCounters
from api.responses import error, error_responses
from services.integrations.cloud_cache import cache_status, sync_cache

router = APIRouter()


@router.get("/api/cloud-db/status", response_model=CloudDbStatus, responses=error_responses(500))
def get_cloud_db_status_api() -> CloudDbStatus:
    """Retourne l'état détaillé du cache local SQLite et de sa synchronisation Firestore."""
    status = cache_status()
    return CloudDbStatus(
        status="success",
        enabled=status.enabled,
        db_exists=status.db_exists,
        db_filename=status.db_filename,
        db_size_kb=status.db_size_kb,
        member_count=status.member_count,
        pending=status.pending,
        last_error="Échec de la dernière synchronisation (détails dans les journaux)." if status.last_sync_failed else "",
        last_sync=status.last_sync,
    )


@router.post("/api/cloud-db/sync", response_model=CloudDbSync, responses=error_responses(500))
def sync_cloud_db_api(force: bool = Query(False)) -> CloudDbSync | JSONResponse:
    """Force la synchronisation bilatérale entre Firestore et la base SQLite locale."""
    result = sync_cache(full=force)
    if result is None:
        return CloudDbSync(status="skipped", message="Réplication Firestore désactivée sur ce serveur (ALJ_CACHE_REPLICATION=off).")
    if result.error_count:
        return error(500, f"Erreur de synchronisation ({result.error_count} erreur(s), détails dans les journaux).")
    counters = SyncCounters(pulled=result.pulled, pushed=result.pushed, full=result.full)
    return CloudDbSync(status="success", message="Base de données SQLite synchronisée avec succès avec Firestore.", result=counters)
