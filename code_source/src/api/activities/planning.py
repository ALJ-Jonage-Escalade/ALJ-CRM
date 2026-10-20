"""Weekly planning of the climbing slots (SQLite cache) and its Excel export."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse, Response

from api.responses import internal_error
from infrastructure.sqlite.repository import SqliteRepository

router = APIRouter()


@router.get("/api/planning")
def get_planning():
    """Récupère le planning depuis la BDD SQLite."""
    try:
        from infrastructure.sqlite.repository import SqliteRepository
        return SqliteRepository.load_planning_data(log_debug=False)
    except Exception as e:
        return {"error": internal_error(e, "get_planning")}


@router.post("/api/planning/item")
def save_planning_item_api(item: Dict[str, Any] = Body(...)):
    """Crée ou met à jour un créneau unique dans la table planning."""
    try:
        from infrastructure.sqlite.repository import SqliteRepository
        saved_item = SqliteRepository.save_planning_item(item)
        return {"status": "success", "message": "Créneau enregistré avec succès.", "item": saved_item}
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": internal_error(e, "save_planning_item_api")})


@router.delete("/api/planning/item/{item_id}")
def delete_planning_item_api(item_id: int):
    """Supprime un créneau de planning par son ID."""
    try:
        from infrastructure.sqlite.repository import SqliteRepository
        ok = SqliteRepository.delete_planning_item(item_id)
        if not ok:
            return JSONResponse(status_code=404, content={"status": "error", "message": f"Créneau #{item_id} introuvable."})
        return {"status": "success", "message": f"Créneau #{item_id} supprimé avec succès."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "delete_planning_item_api")})


@router.get("/api/planning/export")
def export_planning_api(mode: str = Query("grid"), season: Optional[str] = Query(None)):
    """Exporte le planning au format Excel (grille visuelle hebdomadaire ou liste tabulaire)."""
    import os
    import tempfile
    import shutil
    from infrastructure.sqlite.repository import SqliteRepository
    from exports.planning_excel import export_planning_excel, export_planning_list_excel
    from domain.constants import get_active_season

    target_season = season or get_active_season()
    planning_data = SqliteRepository.load_planning_data(log_debug=False)

    tmp_dir = tempfile.mkdtemp(prefix="alj_plan_export_")
    try:
        if mode == "list":
            filename = f"Planning_Liste_{target_season}.xlsx"
            out_path = os.path.join(tmp_dir, filename)
            export_planning_list_excel(planning_data, target_season, out_path)
        else:
            filename = f"Planning_Grille_{target_season}.xlsx"
            out_path = os.path.join(tmp_dir, filename)
            export_planning_excel(planning_data, target_season, out_path)

        with open(out_path, "rb") as f:
            content_bytes = f.read()

        return Response(
            content=content_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/api/planning")
def update_planning(planning_data: List[Dict[str, Any]] = Body(...)):
    """Met à jour le planning dans la BDD SQLite."""
    try:
        SqliteRepository.save_planning_data(planning_data)
        return {"status": "success", "message": "Planning mis à jour"}
    except Exception as e:
        return {"error": internal_error(e, "update_planning")}
