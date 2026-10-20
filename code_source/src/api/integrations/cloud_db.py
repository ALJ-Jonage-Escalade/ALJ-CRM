"""SQLite cache of the crm_* Firestore collections: status and forced sync."""

from __future__ import annotations

import os

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from api.responses import internal_error

router = APIRouter()


@router.get("/api/cloud-db/status")
def get_cloud_db_status_api():
    """Retourne l'état détaillé du cache local SQLite et de sa synchronisation Firestore."""
    try:
        from infrastructure.firestore.cloud_database import CloudDatabase
        from infrastructure.sqlite.repository import SqliteRepository
        enabled = CloudDatabase.is_enabled()
        st = CloudDatabase.status() if enabled else {}
        db_path = SqliteRepository.get_db_path()
        db_exists = os.path.exists(db_path)
        db_size_kb = round(os.path.getsize(db_path) / 1024, 1) if db_exists else 0

        member_count = 0
        if db_exists:
            try:
                conn = SqliteRepository.get_connection()
                row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
                member_count = row[0] if row else 0
                conn.close()
            except Exception:
                pass

        return {
            "status": "success",
            "enabled": enabled,
            "db_exists": db_exists,
            "db_filename": os.path.basename(db_path),
            "db_size_kb": db_size_kb,
            "member_count": member_count,
            "pending": st.get("pending", 0),
            "last_error": st.get("last_error", ""),
            "last_sync": st.get("last_sync"),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "get_cloud_db_status_api")})


@router.post("/api/cloud-db/sync")
def sync_cloud_db_api(force: bool = Query(False)):
    """Force la synchronisation bilatérale entre Firestore et la base SQLite locale."""
    try:
        from infrastructure.firestore.cloud_database import CloudDatabase
        if not CloudDatabase.is_enabled():
            return {"status": "skipped", "message": "Mode Firestore non activé (MEMBER_BACKEND != firestore)."}

        result = CloudDatabase.sync(full=force, force_pull_all=force)
        errors = result.get("errors") if isinstance(result, dict) else []
        if errors:
            return JSONResponse(status_code=500, content={"status": "error", "message": f"Erreur de synchronisation : {'; '.join(errors)}", "result": result})

        return {
            "status": "success",
            "message": "Base de données SQLite synchronisée avec succès avec Firestore.",
            "result": result
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "sync_cloud_db_api")})
