"""Weekly planning of the climbing slots (SQLite cache): the slots, their edits and the Excel export, generated in
memory. Knows nothing about HTTP: refusals are raised as domain.errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from domain.constants import resolve_season
from domain.errors import InvalidRequest, NotFound
from exports.planning_excel import export_planning_excel, export_planning_list_excel
from infrastructure.sqlite.planning import PlanningRepository

PlanningRow = Dict[str, Any]  # Any: a row of the planning table (text, lists, flags)


@dataclass(frozen=True)
class PlanningExport:
    content: bytes
    filename: str


def list_slots() -> List[PlanningRow]:
    return PlanningRepository.load_planning_data()


def save_slot(slot: PlanningRow) -> PlanningRow:
    """Creates the slot, or updates it when it has an id; blank coach names are dropped."""
    if not slot.get("groupe"):
        raise InvalidRequest("Le nom du groupe est obligatoire.")
    if not slot.get("horaires"):
        raise InvalidRequest("Les horaires sont obligatoires.")
    slot = {**slot, "encadrants": [e.strip() for e in slot.get("encadrants") or [] if e.strip()]}
    return PlanningRepository.save_planning_item(slot)


def delete_slot(slot_id: int) -> None:
    if not PlanningRepository.delete_planning_item(slot_id):
        raise NotFound(f"Créneau #{slot_id} introuvable.")


def export_planning(mode: Literal["grid", "list"], season: Optional[str]) -> PlanningExport:
    """The planning as an Excel workbook: a weekly grid, or a list of the slots."""
    target_season = resolve_season(season)
    planning_data = PlanningRepository.load_planning_data()
    if mode == "list":
        return PlanningExport(export_planning_list_excel(planning_data, target_season), f"Planning_Liste_{target_season}.xlsx")
    try:
        content = export_planning_excel(planning_data, target_season)
    except ValueError as e:  # no slot with a single day and readable hours
        raise InvalidRequest("Aucun créneau à placer sur la grille : il faut un jour et des horaires lisibles.") from e
    return PlanningExport(content, f"Planning_Grille_{target_season}.xlsx")
