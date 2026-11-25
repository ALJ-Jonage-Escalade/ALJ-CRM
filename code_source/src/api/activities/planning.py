"""Weekly planning of the climbing slots (SQLite cache) and its Excel export."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from api.activities.schemas import PlanningSlot, PlanningSlotDeleted, PlanningSlotSaved, PlanningSlotUpdate
from api.responses import XLSX, error_responses, file_download
from services.activities import planning

router = APIRouter()


def _slot(row: Dict[str, Any]) -> PlanningSlot:  # Any: a row of the planning table
    """Old rows may hold NULL columns."""
    text = {field: str(row.get(field) or "").strip() for field in PlanningSlot.model_fields
            if field not in ("id", "encadrants", "helloasso_tarifs", "seance_autonome")}
    return PlanningSlot(id=int(row["id"]), encadrants=[str(e) for e in row.get("encadrants") or []],
                        helloasso_tarifs=[str(t) for t in row.get("helloasso_tarifs") or []],
                        seance_autonome=bool(row.get("seance_autonome")), **text)


@router.get("/api/planning", response_model=List[PlanningSlot], responses=error_responses(500))
def get_planning() -> List[PlanningSlot] | JSONResponse:
    """Récupère le planning depuis la BDD SQLite."""
    return [_slot(row) for row in planning.list_slots()]


@router.post("/api/planning/item", response_model=PlanningSlotSaved, responses=error_responses(400, 500))
def save_planning_item_api(item: PlanningSlotUpdate) -> PlanningSlotSaved | JSONResponse:
    """Crée ou met à jour un créneau unique dans la table planning."""
    saved = planning.save_slot(item.model_dump())
    return PlanningSlotSaved(status="success", message="Créneau enregistré avec succès.", item=_slot(saved))


@router.delete("/api/planning/item/{item_id}", response_model=PlanningSlotDeleted, responses=error_responses(404, 500))
def delete_planning_item_api(item_id: int) -> PlanningSlotDeleted | JSONResponse:
    """Supprime un créneau de planning par son ID."""
    planning.delete_slot(item_id)
    return PlanningSlotDeleted(status="success", message=f"Créneau #{item_id} supprimé avec succès.")


@router.get("/api/planning/export", response_class=Response,
            responses={200: {"content": {XLSX: {}}, "description": "Classeur Excel"}, **error_responses(400, 500)})
def export_planning_api(mode: Literal["grid", "list"] = Query("grid"), season: Optional[str] = Query(None)) -> Response:
    """Exporte le planning au format Excel (grille visuelle hebdomadaire ou liste tabulaire)."""
    export = planning.export_planning(mode, season)
    return file_download(export.content, export.filename, XLSX)
