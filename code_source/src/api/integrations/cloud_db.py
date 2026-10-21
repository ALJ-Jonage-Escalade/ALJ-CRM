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
        from infrastructure.sqlite.connection import SqliteDatabase
        enabled = CloudDatabase.is_enabled()
        st = CloudDatabase.status() if enabled else {}
        db_path = SqliteDatabase.get_db_path()
        db_exists = os.path.exists(db_path)
        db_size_kb = round(os.path.getsize(db_path) / 1024, 1) if db_exists else 0

        member_count = 0
        if db_exists:
            try:
                conn = SqliteDatabase.get_connection()
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
            "last_error": "Échec de la dernière synchronisation (détails dans les journaux)." if st.get("last_error") else "",
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

        report = CloudDatabase.sync(full=force, force_pull_all=force)
        if not isinstance(report, dict):
            report = {}
        # Only the counters reach the page: the error texts (Firestore, SQLite) stay in the log
        result = {
            "pulled": int(report.get("pulled") or 0),
            "pushed": int(report.get("pushed") or 0),
            "full": bool(report.get("full")),
        }
        errors = report.get("errors") or []
        if errors:
            for err in errors:
                print(f"❌ [CLOUD_DB] Synchronisation : {err}")
            return JSONResponse(status_code=500, content={
                "status": "error",
                "message": f"Erreur de synchronisation ({len(errors)} erreur(s), détails dans les journaux).",
                "result": result,
            })

        return {
            "status": "success",
            "message": "Base de données SQLite synchronisée avec succès avec Firestore.",
            "result": result
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "sync_cloud_db_api")})
