"""Weekly planning of the climbing slots (SQLite cache) and its Excel export."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from api.activities.schemas import PlanningReplaced, PlanningSlot, PlanningSlotDeleted, PlanningSlotSaved, PlanningSlotUpdate
from api.responses import XLSX, error, error_responses, file_download
from domain.constants import get_active_season, is_valid_season
from exports.planning_excel import export_planning_excel, export_planning_list_excel
from infrastructure.sqlite.planning import PlanningRepository

router = APIRouter()


def _slot(row: Dict[str, Any]) -> PlanningSlot:  # Any: a row of the planning table
    """Old rows may hold NULL columns."""
    text = {field: str(row.get(field) or "").strip() for field in PlanningSlot.model_fields
            if field not in ("id", "encadrants", "helloasso_tarifs")}
    return PlanningSlot(id=int(row["id"]), encadrants=[str(e) for e in row.get("encadrants") or []],
                        helloasso_tarifs=[str(t) for t in row.get("helloasso_tarifs") or []], **text)


@router.get("/api/planning", response_model=List[PlanningSlot], responses=error_responses(500))
def get_planning() -> List[PlanningSlot] | JSONResponse:
    """Récupère le planning depuis la BDD SQLite."""
    return [_slot(row) for row in PlanningRepository.load_planning_data()]


@router.post("/api/planning/item", response_model=PlanningSlotSaved, responses=error_responses(400, 500))
def save_planning_item_api(item: PlanningSlotUpdate) -> PlanningSlotSaved | JSONResponse:
    """Crée ou met à jour un créneau unique dans la table planning."""
    if not item.groupe:
        return error(400, "Le nom du groupe est obligatoire.")
    if not item.horaires:
        return error(400, "Les horaires sont obligatoires.")
    slot = item.model_dump()
    slot["encadrants"] = [e.strip() for e in item.encadrants if e.strip()]
    saved = PlanningRepository.save_planning_item(slot)
    return PlanningSlotSaved(status="success", message="Créneau enregistré avec succès.", item=_slot(saved))


@router.delete("/api/planning/item/{item_id}", response_model=PlanningSlotDeleted, responses=error_responses(404, 500))
def delete_planning_item_api(item_id: int) -> PlanningSlotDeleted | JSONResponse:
    """Supprime un créneau de planning par son ID."""
    if not PlanningRepository.delete_planning_item(item_id):
        return error(404, f"Créneau #{item_id} introuvable.")
    return PlanningSlotDeleted(status="success", message=f"Créneau #{item_id} supprimé avec succès.")


@router.get("/api/planning/export", response_class=Response,
            responses={200: {"content": {XLSX: {}}, "description": "Classeur Excel"}, **error_responses(400, 500)})
def export_planning_api(mode: Literal["grid", "list"] = Query("grid"), season: Optional[str] = Query(None)) -> Response:
    """Exporte le planning au format Excel (grille visuelle hebdomadaire ou liste tabulaire)."""
    target_season = season or get_active_season()
    if not is_valid_season(target_season):
        return error(400, "Saison invalide (format attendu : AAAA-AAAA).")
    planning_data = PlanningRepository.load_planning_data()
    if mode == "list":
        return file_download(export_planning_list_excel(planning_data, target_season), f"Planning_Liste_{target_season}.xlsx", XLSX)
    try:
        content = export_planning_excel(planning_data, target_season)
    except ValueError:  # no slot with a single day and readable hours
        return error(400, "Aucun créneau à placer sur la grille : il faut un jour et des horaires lisibles.")
    return file_download(content, f"Planning_Grille_{target_season}.xlsx", XLSX)


@router.post("/api/planning", response_model=PlanningReplaced, responses=error_responses(500))
def update_planning(slots: List[PlanningSlotUpdate]) -> PlanningReplaced:
    """Remplace le planning complet (administrateurs) ; un créneau d'id 0 reçoit un nouvel identifiant."""
    PlanningRepository.save_planning_data([{**slot.model_dump(), "id": slot.id or None} for slot in slots])
    return PlanningReplaced(status="success", message="Planning mis à jour", count=len(slots))
